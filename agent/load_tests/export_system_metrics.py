# agent/load_tests/export_system_metrics.py
"""
Script thu thập các metrics chuyên sâu từ Prometheus (vLLM, LangGraph Nodes, GPU Cache, Safeguards)
và tích hợp chung với dữ liệu k6 client để tạo file báo cáo toàn diện 360 độ.
Cách dùng:
    python agent/load_tests/export_system_metrics.py --protocol http --minutes 20
    python agent/load_tests/export_system_metrics.py --protocol grpc --minutes 20
"""
import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
from datetime import datetime
# Đảm bảo in UTF-8 không lỗi trên Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
METRIC_QUERIES = {
    # ── 1. vLLM Engine & GPU Metrics ──
    "vllm_llm_gpu_kv_cache_peak_percent": 'max_over_time(vllm:kv_cache_usage_perc{service="vllm-llm"}[{duration}]) * 100',
    "vllm_llm_gpu_kv_cache_avg_percent": 'avg_over_time(vllm:kv_cache_usage_perc{service="vllm-llm"}[{duration}]) * 100',
    "vllm_embed_gpu_kv_cache_peak_percent": 'max_over_time(vllm:kv_cache_usage_perc{service="vllm-embedding"}[{duration}]) * 100',
    "vllm_max_waiting_queue": 'max_over_time(vllm:num_requests_waiting{service="vllm-llm"}[{duration}])',
    "vllm_max_concurrent_running": 'max_over_time(vllm:num_requests_running{service="vllm-llm"}[{duration}])',
    "vllm_prompt_tokens_per_sec": 'avg(rate(vllm:prompt_tokens_total{service="vllm-llm"}[{duration}]))',
    "vllm_generation_tokens_per_sec": 'avg(rate(vllm:generation_tokens_total{service="vllm-llm"}[{duration}]))',
    "vllm_num_preemptions_total": 'sum(increase(vllm:num_preemptions_total{service="vllm-llm"}[{duration}]))',
    # ── 2. LangGraph Cognitive Architecture & Token Governance ──
    "langgraph_safeguard_forced_terminations": 'sum(increase(langgraph_forced_termination_total[{duration}]))',
    "semantic_cache_hit_rate_percent": 'sum(increase(semantic_cache_requests_total{status="hit"}[{duration}])) / (sum(increase(semantic_cache_requests_total[{duration}])) > 0) * 100',
    "node_latency_planner_p95_s": 'histogram_quantile(0.95, sum(rate(agent_node_duration_seconds_bucket{node_name="planner"}[{duration}])) by (le))',
    "node_latency_travel_react_p95_s": 'histogram_quantile(0.95, sum(rate(agent_node_duration_seconds_bucket{node_name="travel_react_agent"}[{duration}])) by (le))',
    "node_latency_evaluator_p95_s": 'histogram_quantile(0.95, sum(rate(agent_node_duration_seconds_bucket{node_name="evaluator_agent"}[{duration}])) by (le))',
    "node_latency_fact_checker_p95_s": 'histogram_quantile(0.95, sum(rate(agent_node_duration_seconds_bucket{node_name="fact_checker"}[{duration}])) by (le))',
    # ── 3. Traffic Stream Concurrency ──
    "peak_active_sse_streams": 'max_over_time(sse_active_streams[{duration}])',
    "peak_active_grpc_streams": 'max_over_time(grpc_active_streams[{duration}])',
}

def query_prometheus(query: str):
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MetricsExporter/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results and "value" in results[0]:
                    val = float(results[0]["value"][1])
                    return round(val, 3)
    except Exception as e:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Export combined k6 + vLLM + System metrics to JSON")
    parser.add_argument("--protocol", choices=["http", "grpc"], default="http", help="Protocol tested (http hoặc grpc)")
    parser.add_argument("--minutes", type=int, default=20, help="Thời gian nhìn lại trong Prometheus (phút)")
    args = parser.parse_args()
    duration = f"{args.minutes}m"
    print(f"📊 Đang thu thập chỉ số vLLM & Hệ thống từ Prometheus ({PROMETHEUS_URL}) trong {duration} qua...")
    system_metrics = {}
    for metric_name, query_template in METRIC_QUERIES.items():
        q = query_template.replace("{duration}", duration)
        val = query_prometheus(q)
        system_metrics[metric_name] = val
        print(f"  ✓ {metric_name:<42}: {val}")
    # Đọc file client-side k6 gần nhất
    k6_file = os.path.join(REPORTS_DIR, f"latest_{args.protocol}_test.json")
    k6_data = {}
    if os.path.exists(k6_file):
        try:
            with open(k6_file, "r", encoding="utf-8") as f:
                k6_data = json.load(f)
            print(f"  ✓ Đã nạp dữ liệu client từ: {k6_file}")
        except Exception as e:
            print(f"  ⚠️ Không đọc được file k6: {e}")
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_report = {
        "metadata": {
            "protocol": args.protocol,
            "export_time": datetime.now().isoformat(),
            "time_window_minutes": args.minutes,
            "prometheus_url": PROMETHEUS_URL
        },
        "vllm_and_system_metrics": system_metrics,
        "k6_client_metrics": k6_data
    }
    out_file = os.path.join(REPORTS_DIR, f"{args.protocol}_full_metrics_{now_str}.json")
    latest_out_file = os.path.join(REPORTS_DIR, f"latest_{args.protocol}_full_metrics.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)
    with open(latest_out_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)
    print(f"\n🎉 Đã xuất thành công báo cáo toàn diện 360 độ:")
    print(f"   📁 {out_file}")
    print(f"   📁 {latest_out_file}")
    
if __name__ == "__main__":
    main()