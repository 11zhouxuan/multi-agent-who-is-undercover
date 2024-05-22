import streamlit as st
import time
import re
from who_is_undercover_backend import WhoIsUndercover,Player

CHINAWARE_WORDS_LIST = [
    {
    "undercover_word": "白瓷",
    "common_word": "青花瓷",
    "prefer_words":['器形',"图案","用途"]
    },
    {
    "undercover_word": "石膏",
    "common_word": "白瓷",
    "prefer_words":['颜色',"质地","耐腐蚀"]
    },
    {
    "undercover_word": "塑像",
    "common_word": "手办",
    "prefer_words":['题材',"工艺","价值"]
    },
    {
    "undercover_word": "电窑",
    "common_word": "柴窑",
    "prefer_words":['用途',"产出","形态结构"]
    },
    {
    "undercover_word": "玻璃",
    "common_word": "瓷器",
    "prefer_words":['质地',"重量","观感"]
    }
    ]

st.set_page_config(initial_sidebar_state='collapsed')

with st.sidebar:
    add_llm = st.selectbox(
        label = "Choose an LLM",
        options=[
            "anthropic.claude-3-sonnet-20240229-v1:0", 
            "anthropic.claude-3-haiku-20240307-v1:0",
            ]
    )

    words_category = st.selectbox(
        label="词语类别",
        options=[
            "中国白瓷",
            "其他"
        ]
    )
    is_stream = st.radio(label="是否使用流式输出",options=["是","否"])


if "game_obj" not in st.session_state:
    st.session_state['game_obj'] = None

if 'is_new_game' not in st.session_state:
    st.session_state.is_new_game = False

if 'is_reset_game' not in st.session_state:
    st.session_state['is_reset_game'] = False

if "is_game_close" not in st.session_state:
    st.session_state['is_game_close'] = False

if "undercover_word" not in st.session_state:
    st.session_state['undercover_word'] = "林丹"

if "common_word" not in st.session_state:
    st.session_state['common_word'] = '李宗伟'


def start_new_game():
    msg = st.toast(f'正在开始新游戏。。。')
    if words_category == "中国白瓷":
        chinaware_words_str = st.session_state.chinaware_words
        g = re.match("卧底词语:(.*?), 平民词语:(.*)",chinaware_words_str)
        undercover_word = g.group(1).strip()
        common_word = g.group(2).strip()

    else:
        undercover_word = st.session_state.undercover_word
        common_word = st.session_state.common_word
    
    second_agent_prefer_words = getattr(st.session_state,"second_agent_prefer_words",None)
    msg = f'卧底词: {undercover_word}, 平民词: {common_word}'
    if second_agent_prefer_words is not None:
        msg += f', 第一轮第二个Agent偏好: {second_agent_prefer_words}'

    st.toast(msg)
    
    # print(st.session_state.second_agent_prefer_words)
    obj = WhoIsUndercover(
        player_num=6,
        common_word=common_word,
        undercover_word=undercover_word,
        llm_model_id=add_llm,
        is_about_chinaware=getattr(st.session_state,"chinaware_words",False),
        second_agent_prefer_words=getattr(st.session_state,"second_agent_prefer_words",None),
        stream = True if is_stream=="是" else False
    )
    st.session_state['game_obj'] = obj
    st.session_state.is_new_game = True
    st.session_state['is_game_close'] = False 

def next_turn():
    # system_console.empty()
    game_obj: WhoIsUndercover = st.session_state['game_obj']
    st.toast(f'Players 正在做陈述。。。')
    for player_statement in game_obj.next_turn_statement():
        player:Player = player_statement['player']
        with palyer_tabs[player.index]:
            # 展示所有的历史消息
            for i,his in enumerate(player.history):
                with st.chat_message('user'):
                    if not game_obj.stream:
                        with st.popover(his['statement']):
                            st.markdown(f"**Thinking:** {his['thinking']}") 
                    else:
                        with st.container(border=True):
                            with st.expander("Thinking",expanded=True if i == len(player.history)-1 else False):
                                st.write_stream(his['thinking'])

                            with st.container(border=True):
                                st.write_stream(his['statement'])
        if player.active:
            st.toast(f'Player {player.player_id} 完成陈述。')
       
    st.toast(f'Players 正在投票。。。')
    # vote 
    with system_console.container():
        st.write(f"第{game_obj.current_turn}轮投票结果")
        res_container = st.empty()
        for player_vote in game_obj.next_turn_vote():
            player: Player = player_vote['player']
            if not game_obj.stream:
                with st.popover(f'Player {player.player_id} 投票给 Player {player.vote_history[-1]["vote"]}'):
                    st.markdown(f"**Thinking:** {player.vote_history[-1]['thinking']}")
            else:
                with st.container(border=True):
                    # st.markdown(f"**Player {player.player_id} Thinking**")
                    with st.expander(f"**Player {player.player_id} Thinking**",expanded=True):
                        st.write_stream(player.vote_history[-1]['thinking'])
                    # vote 比较短，直接输出
                    vote = ""
                    for vote_s in player.vote_history[-1]["vote"]:
                        vote += vote_s
                    with st.container(border=True):
                        st.write(f'Player {player.player_id} 投票给 Player {vote.replace("user_","")}')
            st.toast(f'Player {player.player_id} 完成投票。')
         
        out_player = game_obj.execute_vote_result()
        with res_container.container(border=True):
            st.write(f'Player {out_player.player_id} 被投票出局！')
            game_obj.current_turn += 1
            if game_obj.is_game_close():
                st.toast(f'游戏结束')
                st.write(game_obj.game_status)
                st.write(f'平民词: {game_obj.common_word}, 卧底词: {game_obj.undercover_word}')
                st.balloons()
                st.session_state['is_game_close'] = True


def reset_game():
    st.session_state.is_new_game = False
    game_obj = st.session_state['game_obj']
    if game_obj is not None:
        st.session_state['undercover_word'] = game_obj.undercover_word
        st.session_state['common_word'] = game_obj.common_word


buttons = st.columns(3)
with buttons[0]:
    is_new_game = st.button('New game', on_click=start_new_game,disabled=st.session_state.is_new_game)

with buttons[1]:
    is_next_turn = st.button('Next turn', disabled=not st.session_state.is_new_game or st.session_state['is_game_close'], on_click=next_turn)

with buttons[2]:
    is_reset_game = st.button('Reset game',disabled=not st.session_state.is_new_game,on_click=reset_game)


# print(is_new_game,is_next_turn,is_reset_game)

if st.session_state.is_new_game:
    game_obj: WhoIsUndercover = st.session_state['game_obj']
    players = game_obj.players
    tab_names = []
    for player in players:
        if player.active:
            color = "green"
        else:
            color = "gray"

        tab_names.append(f':{color}[Player {player.player_id}]')

    palyer_tabs = st.tabs(tab_names)

if not st.session_state.is_new_game:
    if words_category == "中国白瓷":
        # 目前只能选择有限的平民或者卧底词语
        def _option_format(undercover_word,common_word):
            return f"卧底词语: {undercover_word}, 平民词语: {common_word}"

        options = [
            _option_format(
                undercover_word=chinaware_dict['undercover_word'],
                common_word = chinaware_dict['common_word']
            )
            for chinaware_dict in CHINAWARE_WORDS_LIST
        ]
        
        st.selectbox(
            label='请选择词组',
            options=options,
            key="chinaware_words"
            )

        for chinaware_dict in CHINAWARE_WORDS_LIST:
            if st.session_state.chinaware_words == _option_format(
                undercover_word=chinaware_dict['undercover_word'],
                common_word = chinaware_dict['common_word']
            ):
                prefer_options = chinaware_dict['prefer_words']
                # st.session_state.second_agent_prefer_words = prefer_options[0]
                st.selectbox(
                    label="请选择第一轮第二个Agent的发言偏好",
                    options=prefer_options,
                    key="second_agent_prefer_words"
                )
                
    else:
        undercover_word = st.text_input(label='卧底词语',key="undercover_word")
        common_word = st.text_input(label='平民词语',key="common_word")


if not st.session_state.is_new_game:
    new_game_alert = st.info(f'请设置平民和卧底词汇, 点击 “New game” 开始游戏。')


system_console = st.container()





