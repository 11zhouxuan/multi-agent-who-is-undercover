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

policy_prompt = open("prompt/policy.txt").read()

prompt_general_statement = open("prompt/describe_general.txt").read()
prompt_chinaware_statement = open("prompt/describe_chinaware.txt").read()
prompt_general_preference_statement = open("prompt/describe_general_preference.txt").read()
prompt_chinaware_preference_statement = open("prompt/describe_chinaware_preference.txt").read()

prompt_general_vote = open("prompt/vote_general.txt").read()
prompt_chinaware_vote = open("prompt/vote_chinaware.txt").read()

chinaware_knowledge = open("prompt/knowledge.txt").read()



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


def build_statement_prompt(word:str,user_id,turn_id,history:list[dict],is_about_chinaware=False,is_second_order=False,second_agent_prefer_words=None):
    if is_about_chinaware:
        if is_second_order:
            logger.info(f'第一轮第二个Agent偏好: {second_agent_prefer_words},user_id: {user_id}')
            return prompt_general_preference_statement.format(
                policy=policy_prompt, 
                word=word, 
                uid=user_id, 
                history=format_history(history).strip(), 
                turn_id=turn_id,
                preference=second_agent_prefer_words,
                knowledge = chinaware_knowledge
            )
        else:
            return prompt_chinaware_statement.format(
                policy=policy_prompt, 
                word=word, 
                uid=user_id, 
                history=format_history(history).strip(), 
                turn_id=turn_id,
                knowledge = chinaware_knowledge
            )
        
    else:
        return prompt_general_statement.format(
            policy=policy_prompt, 
            word=word, 
            uid=user_id, 
            history=format_history(history).strip(), 
            turn_id=turn_id
            )

def build_vote_prompt(word:str,user_id,turn_id,history:list[dict],active_players:list[str],is_about_chinaware=False):
    assert isinstance(active_players,list),active_players
    if is_about_chinaware:
        return prompt_general_vote.format(
            policy=policy_prompt, 
            word=word, 
            uid=user_id, 
            history=format_history(history).strip(), 
            turn_id=turn_id,
            active_players="\n".join(active_players),
            knowledge = chinaware_knowledge
        )
    else:
        return prompt_general_vote.format(
            policy=policy_prompt, 
            word=word, 
            uid=user_id, 
            history=format_history(history).strip(), 
            turn_id=turn_id,
            active_players="\n".join(active_players),
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
                },
                is_about_chinaware=False,
                second_agent_prefer_words=None
                ) -> None:
        assert player_num > 2, player_num
        self.second_agent_prefer_words = second_agent_prefer_words
        self.is_about_chinaware = is_about_chinaware
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
        is_second_order = False 
        if self.current_turn == 1 and player.index == 1:
            is_second_order = True
            
        #  history
        prompt = build_statement_prompt(
            word,
            user_id=player.player_id,
            turn_id=self.current_turn,
            history=self.collect_history(),
            is_about_chinaware=self.is_about_chinaware,
            is_second_order=is_second_order,
            second_agent_prefer_words=self.second_agent_prefer_words
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
            active_players=[f"user_{player_id}" for player_id in self.get_active_player_ids],
            is_about_chinaware=self.is_about_chinaware
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
                statement = None
            else:
                statement = self.player_statement(player)
            yield {
                  'player': player,
                  'current_turn': self.current_turn,
                  'statement': statement
                }