"""
routers/agent.py
----------------
AI Agent 相关 API 占位 / AI Agent API placeholder

当前为空架子，后续接入 DeepSeek API 实现因子策略智能分析
Currently a stub; will be filled in when DeepSeek API integration is implemented.

计划功能 / Planned features:
  POST /api/agent/analyze  — 触发一次分析，读取 simulations.jsonl 统计通过率，
                             调用 DeepSeek API 生成优化建议
                             Trigger analysis: read simulations.jsonl, call DeepSeek,
                             return suggestions for operator/dataset prioritization
  GET  /api/agent/result/{task_id} — 获取异步分析结果 / Get async analysis result
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/analyze")
async def trigger_analyze(body: dict = {}):
    """
    触发 AI 分析（占位，暂未实现）
    Trigger AI analysis — stub, not yet implemented

    后续实现思路 / Implementation plan:
    1. 读取 records/simulations.jsonl，统计各 operator/dataset 组合的通过率
       Read simulations.jsonl, compute pass rate per operator/dataset combo
    2. 调用 DeepSeek API（deepseek-chat，约 ¥1/M tokens）生成建议
       Call DeepSeek API to generate prioritization suggestions
    3. 将结果写入 records/agent_result.json
       Save result to records/agent_result.json
    4. 返回 task_id，前端轮询 /agent/result/{task_id}
       Return task_id; frontend polls /agent/result/{task_id}
    """
    return JSONResponse(
        status_code=501,
        content={
            "message": "AI Agent 功能尚未实现，敬请期待 / AI Agent not yet implemented",
            "planned": "DeepSeek deepseek-chat integration for operator pass-rate analysis",
        },
    )


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    """
    获取分析任务结果（占位）
    Get analysis task result — stub
    """
    return JSONResponse(
        status_code=501,
        content={"message": "Not yet implemented", "task_id": task_id},
    )
