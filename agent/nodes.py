import os
import re
import json
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed
from agent.states import AgentState, SAFE, PASS, ERROR_FEEDBACK
from tools.code_executor import execute_code
from tools.data_clean import DataCleaner
from utils.logger import logger
from utils.path_tool import ensure_dir, get_abs_path
from utils.prompt_loader import load_data_analysis_prompt, load_code_healing_prompt, load_image_analysis_prompt
from utils.image_base64 import encode_images_to_base64
from agent.llm import llm, call_mllm_image
from utils.llm_cache import get_cached_response, store_cached_response
from utils.llm_cache import get_cached_image_response, store_cached_image_response


def analyze_single_chart(chart_path, base64_data, user_prompt):
    """分析单张图片并返回分析结果（带缓存）"""
    chart_name = os.path.basename(chart_path)
    try:
        cached = get_cached_image_response(user_prompt, chart_path)
        if cached is not None:
            logger.info(f"Image cache HIT for {chart_name}")
            return {"chart_name": chart_name, "chart_path": chart_path, "analysis": cached}

        prompt_template = load_image_analysis_prompt()
        prompt = prompt_template.format(user_prompt=user_prompt, chart_name=chart_name)
        description = call_mllm_image(image_url=base64_data, prompt=prompt)
        store_cached_image_response(user_prompt, chart_path, description)
        return {"chart_name": chart_name, "chart_path": chart_path, "analysis": description}
    except Exception as e:
        logger.error(f"图表 {chart_name} 分析失败: {e}")
        return {"chart_name": chart_name, "chart_path": chart_path, "analysis": f"分析失败: {str(e)}"}


# 用于去重：跟踪上一次打印检查点时使用的 retry_count
_last_checkpointer_retry = -1
# 跟踪上一次流式输出时的 retry_count，避免恢复执行时重复打印
_last_stream_retry = -1


def data_clean_node(state: AgentState):
    """
    节点 1: 数据清洗 (Strategy Executor)
    调用 DataCleaner.auto_clean() 自动执行清洗，输出清洗后的文件路径
    """
    logger.info("--- 节点 1: 数据清洗 (Strategy Executor) ---")

    file_path = state.get("file_path")
    cleaning_policy = state.get("cleaning_policy", {})
    output_dir = state.get("output_folder", get_abs_path("output"))

    if not file_path:
        logger.error("缺少 file_path，数据清洗中止")
        return {}

    threshold = cleaning_policy.get("missing_threshold", 0.8)

    cleaner = DataCleaner(file_path=file_path)
    cleaner.profile()
    cleaner.auto_clean(missing_threshold=threshold)

    ensure_dir(output_dir)
    base = os.path.splitext(os.path.basename(file_path))[0]
    ext = file_path.split(".")[-1].lower()
    out_ext = "csv" if ext == "csv" else "xlsx"
    cleaned_path = os.path.join(output_dir, f"{base}_cleaned.{out_ext}")

    cleaner.save_clean_data(cleaned_path, format=out_ext)
    logger.info(f"清洗完成，输出文件: {cleaned_path}，shape: {cleaner.df.shape}")

    # 构建 data_profile 字符串供 LLM 使用
    profile = cleaner.report.get("before", {})
    profile_lines = [
        f"- 数据形状: {profile.get('shape', 'N/A')}",
        f"- 列名: {', '.join(profile.get('columns', []))}",
        f"- 列类型: {profile.get('dtypes', {})}",
        f"- 缺失值数量: {profile.get('missing_count', {})}",
        f"- 缺失值比例(%): {profile.get('missing_percent', {})}",
        f"- 重复行数: {profile.get('duplicated_rows', 'N/A')}",
    ]
    data_profile = "\n".join(profile_lines)

    return {
        "cleaned_file_path": cleaned_path,
        "data_profile": data_profile,
    }


def code_generator_node(state: AgentState):
    """
    节点 2: 代码生成 (Code Generator)
    """
    global _last_checkpointer_retry, _last_stream_retry

    logger.info("--- 节点 2: 代码生成 (Code Generator) ---")

    user_prompt = state.get("user_prompt", "请对数据进行全面探索并绘图")
    data_profile = state.get("data_profile", "暂无数据概况")
    old_code = state.get("generated_code", "")
    feedback = state.get("review_feedback", "")
    execution_log = state.get("execution_log", "")
    current_retries = state.get("retry_count", 0)

    MAX_RETRIES = 3
    if current_retries >= MAX_RETRIES:
        logger.error(f"达到最大重试次数 ({MAX_RETRIES})，强行终止代码生成！")
        return {"review_feedback": "fatal_error: 代码多次修复失败，请人工介入。"}

    is_first_generation = current_retries == 0 and (not feedback or feedback == SAFE)

    _cached_output = None
    if is_first_generation:
        _cached_output = get_cached_response(user_prompt)

    if _cached_output is not None:
        output = _cached_output
        logger.info(f"LLM cache HIT, skipping API call for: {user_prompt[:50]}...")
        _last_checkpointer_retry = current_retries
        _last_stream_retry = current_retries

    elif is_first_generation:
        logger.info("[初次生成] 正在读取基础提示词并注入需求...")

        raw_prompt = load_data_analysis_prompt()
        final_prompt = raw_prompt.format(
            user_prompt=user_prompt,
            data_profile=data_profile
        )

        if _last_checkpointer_retry != current_retries:
            prompt_preview = final_prompt[:200] + "..." if len(final_prompt) > 200 else final_prompt
            print(f"[LLM] Prompt preview: {prompt_preview}")
            _last_checkpointer_retry = current_retries

        logger.info("正在呼叫云端大模型编写代码...")

        output_chunks = []
        if _last_stream_retry != current_retries:
            for chunk in llm.stream(final_prompt):
                print(chunk.content, end="", flush=True)
                output_chunks.append(chunk.content)
            _last_stream_retry = current_retries
        else:
            for chunk in llm.stream(final_prompt):
                output_chunks.append(chunk.content)
        output = "".join(output_chunks)

        store_cached_response(user_prompt, output)

    else:
        retry_num = current_retries
        logger.warning(f"[第 {retry_num} 次重试] 读取 Debug 提示词，启动自愈模式...")

        raw_prompt = load_code_healing_prompt()
        final_prompt = raw_prompt.format(
            old_code=old_code,
            execution_log=execution_log,
            feedback=feedback
        )

        if _last_checkpointer_retry != current_retries:
            prompt_preview = final_prompt[:200] + "..." if len(final_prompt) > 200 else final_prompt
            print(f"自愈提示词预览：{prompt_preview}")
            _last_checkpointer_retry = current_retries

        logger.info("正在呼叫云端大模型编写代码...")

        output_chunks = []
        if _last_stream_retry != current_retries:
            for chunk in llm.stream(final_prompt):
                print(chunk.content, end="", flush=True)
                output_chunks.append(chunk.content)
            _last_stream_retry = current_retries
        else:
            for chunk in llm.stream(final_prompt):
                output_chunks.append(chunk.content)
        output = "".join(output_chunks)

    output_folder = state.get("output_folder", get_abs_path("output"))
    file_path = state.get("file_path", "")
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    code_file_name = f"{base_name}_generated_code.py"
    code_file_path = os.path.join(output_folder, code_file_name)

    if not output or not output.strip():
        logger.error("LLM 返回内容为空，代码生成失败！")
        output = "# LLM 返回内容为空，代码生成失败\nprint('错误：LLM 未返回有效代码')"
    else:
        logger.info(f"LLM 返回代码长度: {len(output)} 字符")

    with open(code_file_path, "w", encoding="utf-8") as f:
        f.write(output)
    logger.info(f"生成的代码已保存至: {code_file_path}")

    return {
        "generated_code": output,
        "review_feedback": "",
        "execution_log": "",
        "retry_count": current_retries + 1
    }


def sanity_checker_node(state: AgentState):
    """节点 3: 安全审查"""
    logger.info("--- 节点 3: 安全审查 (Sanity Checker) ---")
    code = state.get("generated_code", "")

    dangerous_keywords = ["os.remove", "shutil.rmtree", "os.system", "subprocess"]
    for keyword in dangerous_keywords:
        if code and keyword in code:
            logger.error(f"检测到危险指令: {keyword}")
            return {"review_feedback": f"unsafe: 代码包含危险指令 '{keyword}'，请重写！"}

    logger.info("安全检查通过")
    return {"review_feedback": "safe"}


def code_executor_node(state: AgentState):
    """节点 4: 本地执行"""
    logger.info("--- 节点 4: 代码执行 (Code Executor) ---")
    code = state.get("generated_code", "")
    data_file = state.get("cleaned_file_path") or state.get("file_path")
    output_dir = state.get("output_folder")

    result_text, charts = execute_code(code, data_file, output_dir)
    logger.info(f"代码执行完成，生成了 {len(charts)} 个图表")

    return {
        "execution_log": result_text,
        "visualization_paths": charts,
        "current_visualization_paths": charts
    }


def self_reviewer_node(state: AgentState):
    """节点 5: 结果自评"""
    logger.info("--- 节点 5/6: 结果自评 (Self-Reviewer) ---")
    log = state.get("execution_log", "")

    if "Traceback" in log or "执行代码时出错" in log:
        logger.error("代码执行报错，准备打回 LLM 进行自愈重试")
        return {"review_feedback": f"{ERROR_FEEDBACK}: 运行出现异常，请分析执行日志并修改代码。"}

    logger.info("执行结果满意，批准输出报告")
    return {
        "review_feedback": PASS,
        "chart_insights": ["生成的图表逻辑清晰，指标符合预期。"]
    }


def imag_analysis_code(state: AgentState):
    """节点 7: 分析图片"""
    logger.info("--- 节点 7: 分析图片与生成图片内容 (Image Analysis) ---")

    current_charts = state.get("current_visualization_paths", [])
    existing_analysis = state.get("image_analysis_results", [])
    user_prompt = state.get("user_prompt", "请描述这张图表的内容，包括主要发现和Insight")

    analyzed_paths = {item["chart_path"] for item in existing_analysis if item.get("chart_path")}
    new_charts = [c for c in current_charts if c not in analyzed_paths]

    if not new_charts:
        logger.warning("没有新图表需要分析，使用历史分析结果")
        return {"image_analysis_results": existing_analysis}

    logger.info(f"正在将 {len(new_charts)} 张新图表转为 Base64...")
    base64_images = encode_images_to_base64(new_charts)

    analyze_single = partial(analyze_single_chart, user_prompt=user_prompt)

    total = len(new_charts)
    with ThreadPoolExecutor(max_workers=min(4, total)) as pool:
        futures = {pool.submit(analyze_single, chart, b64): (chart, b64) for chart, b64 in zip(new_charts, base64_images)}
        new_analysis_results = [f.result() for f in as_completed(futures)]
    for idx, result in enumerate(new_analysis_results, 1):
        logger.info(f"正在分析图表: {result['chart_name']}")

    all_analysis_results = existing_analysis + new_analysis_results
    logger.info(f"图片分析完成，共处理 {len(all_analysis_results)} 张图表（含历史）")
    return {"image_analysis_results": all_analysis_results}


def report_output_node(state: AgentState):
    """节点 8: 报告生成与持久化"""
    logger.info("--- 节点 8: 报告汇总 (Final Reporter) ---")
    log = state.get("execution_log", "")
    data_profile = state.get("data_profile", "")
    cleaning_policy = state.get("cleaning_policy", {})
    generated_code = state.get("generated_code", "")
    image_analysis_results = state.get("image_analysis_results", [])
    current_charts = state.get("current_visualization_paths", [])

    output_dir = state.get("output_folder")
    report_path = os.path.join(output_dir, "Agent_Final_Report.md")
    report_exists = os.path.exists(report_path)

    existing_content = ""
    existing_chart_names = set()
    turn_number = 1
    if report_exists:
        with open(report_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        existing_chart_names = set(re.findall(r'### (.+)\n!\[.+?\]\(.+?\)', existing_content))
        turn_numbers = re.findall(r'## 第 (\d+) 轮', existing_content)
        if turn_numbers:
            turn_number = max(int(n) for n in turn_numbers) + 1

    user_prompt = state.get("user_prompt", "")
    new_charts = [c for c in current_charts if os.path.basename(c) not in existing_chart_names]
    new_analyses = [a for a in image_analysis_results if a.get("chart_name") not in existing_chart_names]

    if not report_exists:
        # 第一轮：所有内容都放在第一个 turn 里，不再有独立 header
        body = ""
        body += "### 数据概况\n"
        body += f"{data_profile}\n\n" if data_profile else "_暂无数据概况_\n\n"
        body += "### 清洗策略\n"
        body += (f"```json\n{json.dumps(cleaning_policy, indent=2, ensure_ascii=False)}\n```\n\n"
             if cleaning_policy and cleaning_policy.get("strategies") else "_无需清洗或策略为空_\n\n")
        body += "### 生成的代码\n"
        body += f"```python\n{generated_code}\n```\n\n" if generated_code else "_未生成代码_\n\n"
        body += "### 终端执行输出\n"
        body += f"```text\n{log if log else '(无输出)'}\n```\n\n"
        body += "### 可视化图表\n"
        if new_charts:
            for chart in new_charts:
                chart_name = os.path.basename(chart)
                rel_path = os.path.join(os.path.basename(output_dir), chart_name)
                body += f"### {chart_name}\n![{chart_name}]({rel_path})\n\n"
        else:
            body += "_无生成的图表_\n\n"
        body += "### 图片分析\n"
        if new_analyses:
            for item in new_analyses:
                chart_name = item.get("chart_name", "未知图表")
                body += f"### {chart_name}\n{item.get('analysis', '无分析内容')}\n\n"
        else:
            body += "_无图片分析结果_\n\n"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 数据分析智能体报告\n\n## 第 {turn_number} 轮：{user_prompt}\n\n{body}")
    else:
        # 后续轮：追加新轮次块
        md = f"## 第 {turn_number} 轮：{user_prompt}\n\n"
        md += "### 可视化图表\n"
        if new_charts:
            for chart in new_charts:
                chart_name = os.path.basename(chart)
                rel_path = os.path.join(os.path.basename(output_dir), chart_name)
                md += f"### {chart_name}\n![{chart_name}]({rel_path})\n\n"
            for item in new_analyses:
                chart_name = item.get("chart_name", "未知图表")
                md += f"### {chart_name}\n{item.get('analysis', '无分析内容')}\n\n"
            logger.info(f"已追加第 {turn_number} 轮 ({len(new_charts)} 张新图表) 到报告")
        else:
            md += "_无新图表_\n\n"
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(md)

    logger.info(f"报告已更新 (第 {turn_number} 轮): {report_path}")

    turn_record = {
        "user_prompt": user_prompt,
        "turn_number": turn_number,
        "generated_code": generated_code,
        "execution_log": log,
        "charts": current_charts,
        "chart_insights": state.get("chart_insights", []),
        "output_folder": output_dir,
    }
    return {"chat_history": [turn_record]}