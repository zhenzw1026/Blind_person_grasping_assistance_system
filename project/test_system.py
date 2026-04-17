#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系统功能测试脚本
"""

from grasp_assist.pipeline import GraspAssistPipeline
from grasp_assist.config import load_config

# 测试简体转换
print("=" * 60)
print("测试 1: 繁体到简体转换")
print("=" * 60)

cfg = load_config("configs/default.yaml")
pipeline = GraspAssistPipeline(cfg, enable_audio=False)

test_texts = [
    "幫我找手機",
    "查找鍵盤",
    "找書籍",
    "我要找杯子",
]

for text in test_texts:
    simplified = pipeline.simplified_chinese(text)
    print(f"原文: {text:<15} -> 简体: {simplified}")

# 测试物品提取
print("\n" + "=" * 60)
print("测试 2: 物品名称提取")
print("=" * 60)

test_commands = [
    "帮我找手机",
    "我要找杯子",
    "查找钥匙",
    "鼠标在哪",
    "找眼镜",
    "拿一下书",
    "帮我找水杯",
    "手机",
]

for cmd in test_commands:
    cn_word, en_label = pipeline.extract_target_from_text(cmd)
    if cn_word:
        print(f"✓ 命令: {cmd:<15} -> 物品: {cn_word} ({en_label})")
    else:
        print(f"✗ 命令: {cmd:<15} -> 无法识别")

# 测试物品库
print("\n" + "=" * 60)
print("测试 3: 可用物品清单")
print("=" * 60)

print(f"总共支持 {len(pipeline.label_map_cn2en)} 个物品名称：\n")

# 按英文分类显示
categories = {}
for cn_word, en_label in pipeline.label_map_cn2en.items():
    if en_label not in categories:
        categories[en_label] = []
    categories[en_label].append(cn_word)

for en_label in sorted(categories.keys()):
    cn_words = ", ".join(categories[en_label])
    print(f"  {en_label:<15} : {cn_words}")

print("\n" + "=" * 60)
print("✓ 系统测试完成！")
print("=" * 60)
