import random
import uuid
import time
from pydantic import BaseModel,Field
from langchain_community.chat_models.bedrock import BedrockChat
from langchain_core.messages import SystemMessage,AIMessage,HumanMessage 
import re 
from functools import partial
import os
from typing import Iterable
import threading   
from queue import Queue  
from collections import defaultdict
import boto3
from logger import get_logger
logger = get_logger("backend")

open_utf8 = partial(open,encoding='utf-8')

policy_prompt = open_utf8("prompt/policy.txt").read()

prompt_general_statement = open_utf8("prompt/describe_general.txt").read()
prompt_chinaware_statement = open_utf8("prompt/describe_chinaware.txt").read()
prompt_general_preference_statement = open_utf8("prompt/describe_general_preference.txt").read()
prompt_chinaware_preference_statement = open_utf8("prompt/describe_chinaware_preference.txt").read()

prompt_general_vote = open_utf8("prompt/vote_general.txt").read()
prompt_chinaware_vote = open_utf8("prompt/vote_chinaware.txt").read()

chinaware_knowledge = open_utf8("prompt/knowledge.txt").read()



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
        return prompt_chinaware_vote.format(
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



class MyString:
    def __init__(self,gen:Iterable[str],player:Player,msg_type="thinking"):
        self.gen = gen  
        self.player = player 
        self.msg_type = msg_type
        self.s = ""
        self.is_gen_close = False
    
    def __iter__(self):
        if  not self.is_gen_close:
            for i in self.gen:
                self.s += i['chunk']
                yield i['chunk']
            logger.info("\n" + f"{self.msg_type}: {self.s}")
            self.is_gen_close = True
        else:
            yield self.s
        
    def __str__(self):
        return self.s 

    __repr__ = __str__

    

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
                second_agent_prefer_words=None,
                stream=True
                ) -> None:
        assert player_num > 2, player_num
        self.second_agent_prefer_words = second_agent_prefer_words
        self.is_about_chinaware = is_about_chinaware
        self.stream = stream
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

    
    def call_llm(self,prompt:str,prefill="",stream=True):
        messages = [HumanMessage(content=prompt)]
        if prefill:
            messages.append(AIMessage(content=prefill))
        
        if stream:
            return self.llm.stream(messages)
        else:
            r = self.llm.invoke(messages)
            return r.content


    def collect_history(self):
        history = [{} for _ in range(self.current_turn)]
        for player in self.players:
            for his in player.history:
                history[his['turn']-1][player.player_id] = str(his['statement'])
        return history

    @staticmethod 
    def check_subendwiths(cur_s:str,end_s:str):
        for i in range(1,len(end_s)+1):
            if cur_s.endswith(end_s[:i]):
                return True
        return False


    def llm_stream_helper(self,res:Iterable):
        """
        分别返回thinking和output迭代器

        Args:
            res (Iterable): _description_
        """
        thinking_queue = Queue()
        output_queue = Queue()
        
        def _inner():
            thinking_close_flag = False
            output_start_flag = False 
            # output_close_flag = False 
            current_str = ""
            for r in res:
                current_str += r.content
                if not thinking_close_flag:
                    # 还处于thinking中
                    if self.check_subendwiths(current_str,"</thinking>"):
                        if "</thinking>" in current_str:
                            # 到了thinking 结尾
                            thinking_close_flag = True
                            splits = current_str.split("</thinking>")
                            thinking_queue.put({
                                    "type":"thinking",
                                    "chunk": splits[0]
                                })
                            
                            thinking_queue.put(None)
                            
                            current_str = splits[1]
                    else:
                        thinking_queue.put({
                                    "type":"thinking",
                                    "chunk": current_str
                                })
                        current_str = ""
                else:
                    # 处于output中
                    if not output_start_flag:
                        if "<output>" in current_str:
                            # 开始进行output输出
                            output_start_flag = True 
                            splits = current_str.split('<output>')
                            # output_queue.put({
                            #     "type":"output",
                            #     "chunk": splits[-1]
                            # })
                            current_str = splits[-1]
                    else:
                        if self.check_subendwiths(current_str,"</output>"):
                            if "</output>" in current_str:
                                # output_close_flag = True
                                splits = current_str.split("</output>")
                                output_queue.put({
                                    "type":"output",
                                    "chunk": splits[0]
                                })
                                output_queue.put(None)
                                return 
                        else:
                            output_queue.put({
                                    "type":"output",
                                    "chunk": current_str
                                })
                            current_str = ""

        def think_gen():
            while True:
                data = thinking_queue.get()
                if data is None:
                    break 
                yield data
        
        def output_gen():
            while True:
                data = output_queue.get()
                if data is None:
                    break 
                yield data

        threading.Thread(target=_inner).start()
        return think_gen(),output_gen()


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
        logger.info(f"\n{prompt}")
        content = self.call_llm(prompt,prefill="<thinking>",stream=self.stream)
        
        if not self.stream:
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
        else:
            think_g, output_g = self.llm_stream_helper(content)
            logger.info(
                "\n" + "="*25 + f"player: {player.player_id}, turn: {self.current_turn}, word: {player.word} statement" + "="*25 
            )
            player.history.append({
                "turn": self.current_turn,
                "statement": MyString(output_g,player=player,msg_type="statement"),
                "thinking": MyString(think_g,player=player,msg_type="thinking")
            })
            return output_g


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
        logger.info(f"\n{prompt}")
        content = self.call_llm(prompt,prefill="<thinking>")
        if not self.stream:
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
        else:
            think_g, output_g = self.llm_stream_helper(content)
            logger.info(
                "\n" + "="*25 + f"player: {player.player_id}, turn: {self.current_turn}, word: {player.word} vote" + "="*25 
            )
            player.vote_history.append({
                "turn": self.current_turn,
                "vote": MyString(output_g,player=player,msg_type="vote"),
                "thinking": MyString(think_g,player=player,msg_type='thinking')
            })
            return output_g


    @property
    def get_active_player_ids(self):
        return [player.player_id for player in self.players if player.active]

    
    def find_vote_result(self):
        votes = defaultdict(int)
        for player in self.players:
            if player.vote_history[-1]['turn'] == self.current_turn:
                votes[str(player.vote_history[-1]['vote']).replace("user_","")] += 1
        
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
            vote = self.player_vote(player)
            yield {
                  'player': player,
                  'current_turn': self.current_turn,
                #   'vote':
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
                #   'statement': statement
                }