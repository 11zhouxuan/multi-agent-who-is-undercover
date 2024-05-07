# multi-agent-who-is-undercover
基于LLM multi agents的《谁是卧底》游戏模拟。


## 安装
```pip install -r requirements.txt```

## 定义AWS环境变量 
在本地文件夹生成 **.env** 文件, 并写入下面的内容:

```
AWS_ACCESS_KEY_ID="xxxxx"
AWS_SECRET_ACCESS_KEY="xxxxx"
AWS_REGION="xxxxxx"
```

## 运行
```streamlit run who_is_undercover_frontend.py```

## 游戏截图
### 游戏开始
![alt text](./doc/start.png)

### 投票可视化
![alt text](./doc/running.png)

