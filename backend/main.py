# -*- coding: utf-8 -*-
"""启动后端：python backend/main.py  或  python main.py（backend 目录下）"""
import uvicorn

if __name__ == "__main__":
    print("后端 API：http://127.0.0.1:8000   API 文档：http://127.0.0.1:8000/docs")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
