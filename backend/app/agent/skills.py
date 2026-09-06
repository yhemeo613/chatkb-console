# -*- coding: utf-8 -*-
"""
技能系统：目录下的 JSON 即技能，可热加载。

技能 = 场景化的提示词增强包（匹配关键词 + 追加系统提示 + 示例范例）。
新增技能无需改代码：把 xxx.json 丢进 skills 目录即可。
"""
import json
import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_cache: list[dict] | None = None

BUILTIN_SKILLS = {
    "职场沟通": {
        "match": ["领导", "老板", "同事", "加班", "汇报", "工作", "开会", "绩效", "升职", "甲方", "客户"],
        "prompt": "职场场景纪律：对领导不卑不亢，谢意具体、归功协作；对同事友善但有边界；"
                  "不吐槽公司，不越级表功；涉及承诺时留有余地。",
        "example": "谢谢领导，主要是大家把边界问题都兜住了，我把流程理顺了。",
    },
    "长辈沟通": {
        "match": ["妈", "爸", "爷爷", "奶奶", "姥姥", "姥爷", "叔", "姨", "舅", "长辈", "爸妈"],
        "prompt": "长辈场景纪律：语气亲昵但不敷衍；对养生/时事观点顺着说；多用具体细节回应关心；"
                  "结尾主动给一个行动承诺（如周末打电话、回家吃饭）。",
        "example": "知道啦妈，这周末我回家吃饭，你想吃啥我买回去。",
    },
    "婉拒请求": {
        "match": ["帮忙", "借", "帮个忙", "周转", "搭把手", "代购", "顺路", "投屏", "砍一刀"],
        "prompt": "拒绝场景纪律：三明治法——先谢/先共情，再给出不带攻击性的明确拒绝和简短理由，"
                  "最后给台阶或替代方案。理由只给一个，不解释过多。涉及金钱一律只拖延不承诺。",
        "example": "谢谢你想到我！这周我确实排满了，下周节奏正常了你再找我，别客气。",
    },
    "安慰倾听": {
        "match": ["难过", "累", "哭", "分手", "吵架", "烦", "压力", "挂了", "没过", "生病"],
        "prompt": "安慰场景纪律：先接情绪再讲道理（或干脆不讲道理）；禁止「至少你还…」句式；"
                  "不说教、不急于给方案；给陪伴承诺而不是建议清单。",
        "example": "这确实挺让人心累的……想吐槽随时找我，我都在。",
    },
    "邀约应答": {
        "match": ["有空吗", "吃饭", "聚会", "约", "喝酒", "唱歌", "婚礼", "出差"],
        "prompt": "邀约场景纪律：能去就爽快答应并确认时间地点；不能去就感谢+简短理由+改期提议；"
                  "回复里体现你真的看了邀约内容。",
        "example": "周六中午可以！老地方见？我带瓶酒。",
    },
}


def load_skills(force: bool = False) -> list[dict]:
    """扫描目录：内置技能 + JSON 自定义技能（同名覆盖内置）"""
    global _cache
    if _cache is not None and not force:
        return _cache

    merged: dict[str, dict] = {}
    for name, skill in BUILTIN_SKILLS.items():
        merged[name] = {"name": name, "source": "builtin", **skill}

    if SKILLS_DIR.exists():
        for f in sorted(SKILLS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("name") or f.stem
                merged[name] = {
                    "name": name, "source": "custom",
                    "match": data.get("match", []),
                    "prompt": data.get("prompt", ""),
                    "example": data.get("example", ""),
                }
            except Exception:
                continue  # 坏文件跳过，不阻塞启动

    _cache = list(merged.values())
    return _cache


def match_skills(text: str) -> list[dict]:
    """按关键词匹配命中的技能（全部命中项叠加；无命中返回空列表）"""
    hits = []
    for skill in load_skills():
        for kw in skill.get("match", []):
            if kw and kw in text:
                hits.append(skill)
                break
    return hits


def default_skill() -> dict:
    """无命中时的兜底技能"""
    return {
        "name": "通用高情商", "source": "builtin",
        "prompt": "通用纪律：先接住对方情绪/意图，再给出回应；像真人发微信，口语化、短句；"
                  "不用书面语和客套套话；长度一般不超过两三句。",
        "example": "",
    }


def skill_prompt(text: str) -> str:
    """把命中技能拼成可附加的系统提示"""
    hits = match_skills(text)
    if not hits:
        hits = [default_skill()]
    parts = []
    for h in hits:
        parts.append(f"【技能·{h['name']}】{h.get('prompt', '')}")
        if h.get("example"):
            parts.append(f"参考范例：{h['example']}")
    return "\n".join(parts)
