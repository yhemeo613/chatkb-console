# -*- coding: utf-8 -*-
"""编排画布配置：唯一事实来源是 agent/flow.py 的 v2 工作流模板（本模块做转发兼容）"""
from .flow import load_flow_template, save_flow_template


def load_canvas() -> dict:
    return load_flow_template()


def save_canvas(cfg: dict):
    save_flow_template(cfg)


def node_cfg(node_id: str) -> dict:
    for n in load_canvas()["nodes"]:
        if n["id"] == node_id:
            return n
    return {}
