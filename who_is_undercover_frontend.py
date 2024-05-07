import dotenv
dotenv.load_dotenv('.env')
import streamlit as st
import time
from who_is_undercover_backend import WhoIsUndercover,Player

st.set_page_config(initial_sidebar_state='collapsed')

with st.sidebar:
    add_llm = st.selectbox(
        label = "Choose an LLM",
        options=[
            "anthropic.claude-3-sonnet-20240229-v1:0", 
            "anthropic.claude-3-haiku-20240307-v1:0",
            ]
    )

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
    undercover_word = st.session_state.undercover_word
    common_word = st.session_state.common_word
    msg.toast(f'卧底词: {undercover_word}, 平民词: {common_word}')

    obj = WhoIsUndercover(
        player_num=6,
        common_word=common_word,
        undercover_word=undercover_word,
        llm_model_id=add_llm
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
        if player.active:
            st.toast(f'Player {player.player_id} 完成陈述。')
       
        with palyer_tabs[player.index]:
            for his in player.history:
                with st.chat_message('user'):
                    
                    with st.popover(his['statement']):
                        st.markdown(f"**Thinking:** {player.history[-1]['thinking']}") 
                

    st.toast(f'Players 正在投票。。。')
    # vote 
    with system_console.container():
        st.write(f"第{game_obj.current_turn}轮投票结果")
        for player_vote in game_obj.next_turn_vote():
            player: Player = player_vote['player']
            with st.popover(f'Player {player.player_id} 投票给 Player {player_vote["vote"]}'):
                
                st.markdown(f"**Thinking:** {player.vote_history[-1]['thinking']}")

            st.toast(f'Player {player.player_id} 完成投票。')
         
        out_player = game_obj.execute_vote_result()
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
    undercover_word = st.text_input(label='卧底词语',key="undercover_word")
    common_word = st.text_input(label='平民词语',key="common_word")


if not st.session_state.is_new_game:
    new_game_alert = st.info(f'请设置平民和卧底词汇, 点击 “New game” 开始游戏。')


system_console = st.container()





