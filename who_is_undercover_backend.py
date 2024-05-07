import random
import uuid
import time
from pydantic import BaseModel,Field
from langchain_community.chat_models.bedrock import BedrockChat
from langchain_core.messages import SystemMessage,AIMessage,HumanMessage 
import re 
import os
from collections import defaultdict
import boto3
from logger import get_logger
logger = get_logger("backend")

policy_prompt = '''《谁是卧底》是一款多人社交推理游戏。在这个版本中，共有6名玩家参与。
游戏开始时，游戏主持人会为每位玩家分配一个身份和一个词语。玩家的身份分为“平民”和“卧底”。在这个游戏中，有5个平民和1个卧底。
在游戏中，所有平民玩家会得到相同的词语，而卧底玩家的词语会与平民玩家的词语相关但不完全相同。
平民玩家需要尽可能找出谁是卧底，然后在投票环节集中将卧底投出去。
卧底玩家要尽可能隐藏自己卧底身份。
游戏开始后，每位玩家轮流描述自己得到的词语，但不能直接提及该词。所有玩家都需要通过其他玩家的描述，进行分析和推理，以找出可能是卧底的人。
每轮描述结束后，所有玩家投票选择他们认为最可疑的玩家，得票最多的玩家被淘汰。如果淘汰的是卧底，则游戏结束，平民方获胜；如果淘汰的是平民，则游戏继续进行，直到卧底被淘汰，或者卧底和平民的人数相等。此时，卧底方获胜。
'''.strip()


prompt_statement = '''
现在你是一名《谁是卧底》游戏中的玩家，

这款游戏的规则如下：
<policy>
{policy}
</policy>
在描述时有一些要求：
- 在你描述词语时，尽量用模糊的方式描述，不要直接提及词语。
- 保持回答简洁，并使用一些模棱两可的词汇，让其他玩家难以准确判断你的身份。
- 你的描述请保持一句话。
- 一次描述只描述一个特征。
- 不可以和历史发言重复。

你拿到的词语是：
{word}

下面是各个玩家的发言，你是user_{uid}
<history>
{history}
</history>

现在是第{turn_id}轮游戏的描述环节（turn_{turn_id}），请先在<thinking></thinking>xml tag中写出你的分析，例如，你猜测每个玩家拿到了什么词；根据你拿到的词和其他玩家的词，判断你是普通玩家还是卧底。
然后在<output></output>xml tag中给出你的描述。如果你认为自己是卧底，注意隐藏自己的身份。
'''.strip()


prompt_vote = '''
现在你是一名《谁是卧底》游戏中的玩家
《谁是卧底》游戏的规则如下：
<policy>
{policy}
</policy>

你拿到的词语是：{word}

下面是各个玩家的发言，你是user_{uid}
<history>
{history}
</history>


现在是第{turn_id}轮游戏的投票环节（turn_{turn_id}）.
当前还在场上的玩家有:
<active_players>
{active_players}
</active_players>
请先在<thinking></thinking>xml tag中写出你的分析，例如，你猜测每个玩家拿到了什么词；根据你拿到的词和其他玩家的词，判断你是普通玩家还是卧底；如果你不是卧底，找到最像卧底的那个玩家。如果你是卧底，找到除你之外最像卧底的那个玩家。
然后在<output></output>xml tag中给出你认为是卧底的玩家。你必须从还在场上的玩家中，也就是:
<active_players>
{active_players}
</active_players>
选择一位进行投票，不可以弃权。也不可以投票给你自己。
'''.strip()


def format_history(history:list[dict]):
    cur_history = ''
    for his_idx, his_turn in enumerate(history):
        cur_turn = ''
        for his_user_idx,his_user_turn in his_turn.items():
            cur_turn += f'<user_{his_user_idx}>\n{his_user_turn}\n</user_{his_user_idx}>\n'
        if len(cur_turn):
            cur_turn_history = f'<turn_{his_idx+1}>\n' + cur_turn + f'</turn_{his_idx+1}>'
            cur_history += '\n' + cur_turn_history
    return cur_history


def build_statement_prompt(word:str,user_id,turn_id,history:list[dict]):
    return prompt_statement.format(
        policy=policy_prompt, 
        word=word, 
        uid=user_id, 
        history=format_history(history).strip(), 
        turn_id=turn_id
        )

def build_vote_prompt(word:str,user_id,turn_id,history:list[dict],active_players:list[str]):
    assert isinstance(active_players,list),active_players
    return prompt_vote.format(
        policy=policy_prompt, 
        word=word, 
        uid=user_id, 
        history=format_history(history).strip(), 
        turn_id=turn_id,
        active_players="\n".join(active_players)
        )

class Player(BaseModel):
    index: int 
    player_id: str
    word: str
    active: bool = True,
    history: list[dict] = Field(default_factory=lambda :[])
    is_undercover: bool
    vote_history: list[dict] = Field(default_factory=lambda :[])


class WhoIsUndercover:
    def __init__(self,
                 player_num=6,
                 common_word="夜宵",
                 undercover_word="烧烤",
                 llm_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                 llm_model_kwargs =  { 
                        "max_tokens": 4096,
                        "temperature": 0.0,
                        "top_k": 50,
                        "top_p": 1,
                        "stop_sequences": ["\n\nHuman:", "\n\nAssistant"],
                        "anthropic_version": "bedrock-2023-05-31"
                }
                ) -> None:
        assert player_num > 2, player_num
        self.player_num = player_num
        self.common_word = common_word
        self.undercover_word = undercover_word
        words = [common_word]*(player_num-1) + [undercover_word]
        random.shuffle(words)

        self.players:list[Player] = []

        for index,word in enumerate(words):
            self.players.append(
                Player(
                    index=index,
                    player_id=str(index+1),
                    word=word,
                    is_undercover = word == undercover_word,
                    active=True,
                    history=[]
            ))

        self.game_id = uuid.uuid4()
        self.current_turn = 1 
        self.llm = self.create_llm_model(llm_model_id,llm_model_kwargs)
        self.game_status = "running"

    @classmethod
    def new_game(cls,
                 player_num=6,
                 common_word="夜宵",
                 undercover_word="烧烤"):
        return cls(
            player_num=player_num,
            common_word=common_word,
            undercover_word=undercover_word
            )

    def create_llm_model(self,model_id,model_kwargs):
        region = os.environ.get('AWS_REGION','us-west-2')
        session = boto3.Session(
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
            region_name=region
            )
        client = session.client(
                    "bedrock-runtime", region_name=region
                )
        llm = BedrockChat(
            client=client,
            # credentials_profile_name="atl",
            model_id=model_id,
            model_kwargs=model_kwargs
        )
        return llm

    
    def call_llm(self,prompt:str,prefill=""):
        messages = [HumanMessage(content=prompt)]
        if prefill:
            messages.append(AIMessage(content=prefill))
        r = self.llm.invoke(messages)
        return r.content


    def collect_history(self):
        history = [{} for _ in range(self.current_turn)]
        for player in self.players:
            for his in player.history:
                history[his['turn']-1][player.player_id] = his['statement']
        return history

    def player_statement(self, player:Player):
        word = player.word

        #  history
        prompt = build_statement_prompt(
            word,
            user_id=player.player_id,
            turn_id=self.current_turn,
            history=self.collect_history()
        )
        content = self.call_llm(prompt,prefill="<thinking>")

        result = '<thinking>' + content

        thinking = re.findall("<thinking>(.*?)</thinking>",result,re.S)[0].strip()
        statement = re.findall("<output>(.*?)</output>",result,re.S)[0].strip()
         
        player.history.append({
            "turn": self.current_turn,
            "statement": statement,
            "thinking": thinking
        })
        logger.info(
            "\n" + "="*25 + f"player: {player.player_id}, turn: {self.current_turn}, word: {player.word} " + "="*25 \
            + "\n" + f"thinking: {thinking}" \
            + "\n" + f"statement: {statement}"
            )
        return statement

    def player_vote(self, player:Player):
        word = player.word
        #  history
        prompt = build_vote_prompt(
            word=word,
            user_id=player.player_id,
            turn_id=self.current_turn,
            history=self.collect_history(),
            active_players=[f"user_{player_id}" for player_id in self.get_active_player_ids]
        )
        content = self.call_llm(prompt,prefill="<thinking>")
        result = '<thinking>' + content

        thinking = re.findall("<thinking>(.*?)</thinking>",result, re.S)[0].strip()
        vote = re.findall("<output>(.*?)</output>",result, re.S)[0].replace("user_","").strip()
        player.vote_history.append({
            "turn": self.current_turn,
            "vote": vote,
            "thinking": thinking
        })
        logger.info(
            "\n" + "="*25 + f"player: {player.player_id}, turn: {self.current_turn}, word: {player.word} " + "="*25 \
            + "\n" + f"thinking: {thinking}" \
            + "\n" + f"vote: {vote}"
            )
        return vote


    @property
    def get_active_player_ids(self):
        return [player.player_id for player in self.players if player.active]

    
    def find_vote_result(self):
        votes = defaultdict(int)
        for player in self.players:
            if player.vote_history[-1]['turn'] == self.current_turn:
                votes[player.vote_history[-1]['vote']] += 1
        
        votes_sorted = sorted(list(votes.items()),key=lambda x:x[1],reverse=True)
        vote_res = votes_sorted[0][0]

        active_player_ids = self.get_active_player_ids
        assert vote_res  in active_player_ids, (vote_res,active_player_ids)
        return vote_res

    def execute_vote_result(self):
        vote_res = self.find_vote_result()
        for player in self.players:
            if player.player_id == vote_res:
                player.active = False  
                return player
        
    def get_undercover_player(self):
        for player in self.players:
            if player.is_undercover:
                return player

    def is_game_close(self):
        undercover_player = self.get_undercover_player()
        if not undercover_player.active:
            self.game_status = f"卧底 Player {undercover_player.player_id} 被找到，平民胜利！"
            return True 

        if len(self.get_active_player_ids) <= 3:
            self.game_status = f"当前Player数量小于等于3个，卧底 Player {undercover_player.player_id} 胜利！"
            return True 

        return False 

    
    def next_turn_vote(self):
        for player in self.players:
            if not player.active:
                continue
            yield {
                  'player': player,
                  'current_turn': self.current_turn,
                  'vote':self.player_vote(player)
                }
    
    def next_turn_statement(self):
        for player in self.players:
            if not player.active:
                continue
            yield {
                  'player': player,
                  'current_turn': self.current_turn,
                  'statement':self.player_statement(player)
                }