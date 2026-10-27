// load_tests/http_stream_test.js
// Step-up capacity & RAG/LangGraph load test over FastAPI SSE (/api/chat/stream)
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const e2eLatencyTrend = new Trend('custom_e2e_duration_ms', true);
const ttfbTrend = new Trend('custom_ttfb_ms', true);
const errorRate = new Rate('custom_errors');
const chunksCounter = new Counter('custom_sse_chunks_total');

const BASE_URL = __ENV.AGENT_HTTP_URL || 'http://agent_api:8080';
const CACHE_MODE = __ENV.CACHE_MODE || 'mixed'; // 'unique' (stress LLM/RAG) | 'mixed' (realistic cache hit rate)

const BOOKING_PROMPTS = [
    // Low complexity / Direct executor + Hotel RAG tool
    "Tìm giúp mình khách sạn 5 sao ở Đà Nẵng gần biển Mỹ Khê dưới 4 triệu VND/đêm có hồ bơi vô cực.",
    "Recommend top 3 family-friendly resorts in Nha Trang with a kids club and airport shuttle.",
    "Có khách sạn nào ở trung tâm Quận 1 TP.HCM phù hợp đi công tác, giá dưới 2.5 triệu/đêm không?",
    "Find a romantic boutique hotel in Hoi An Ancient Town with free breakfast and river view.",
    "Khách sạn nào ở Phú Quốc có bãi biển riêng và dịch vụ spa tốt cho cặp đôi hưởng tuần trăng mật?",
    // Medium/High complexity / Planner + Multi-step ReAct + Evaluator + Synthesizer
    "Lập lịch trình du lịch Đà Nẵng - Hội An 4 ngày 3 đêm cho gia đình 4 người (2 người lớn, 2 trẻ em), ngân sách 20 triệu VND, kèm gợi ý khách sạn.",
    "Plan a 5-day luxury itinerary in Phu Quoc for a couple with a $1500 budget, including hotel recommendations and dining.",
    "So sánh ưu nhược điểm giữa việc nghỉ dưỡng ở khu vực Bãi Dài Cam Ranh và trung tâm thành phố Nha Trang, kèm gợi ý khách sạn 4-5 sao.",
    // Support / FAQ path (Tier-1 fast model)
    "Làm thế nào để hủy đặt phòng và kiểm tra chính sách hoàn tiền trên hệ thống?",
    "How can I update my guest contact information and view my booking receipt?",
];

export const options = {
    // Step-up ramp to identify concurrency knee point on a single 24GB GPU (vast.ai)
    stages: [
        { duration: '20s', target: 4 },   // Warm-up / low load
        { duration: '40s', target: 8 },   // Normal load
        { duration: '40s', target: 16 },  // High load (tests vLLM continuous batching & KV cache)
        { duration: '30s', target: 24 },  // Peak stress (monitors queue waiting & preemptions)
        { duration: '15s', target: 0 },   // Cool-down
    ],
    thresholds: {
        http_req_failed: ['rate<0.05'],
        custom_errors: ['rate<0.05'],
        custom_e2e_duration_ms: ['p(95)<25000'],
    },
};

export default function () {
    const url = `${BASE_URL}/api/chat/stream`;
    // Use anon_ prefix so load testing does not flood Redis checkpointer or RabbitMQ extraction queue
    const userId = `anon_k6_user_${__VU}`;
    const sessionId = `loadtest_session_${__VU}_${__ITER}`;

    const basePrompt = BOOKING_PROMPTS[(__VU + __ITER) % BOOKING_PROMPTS.length];
    // In 'unique' mode every request has a unique tag to bypass semantic cache;
    // in 'mixed' mode 30% of requests repeat canonical prompts to measure Semantic Cache hit rate.
    const prompt = (CACHE_MODE === 'unique' || (__ITER % 3 !== 0))
        ? `${basePrompt} [ref:${__VU}-${__ITER}]`
        : basePrompt;

    const payload = JSON.stringify({
        user_id: userId,
        session_id: sessionId,
        prompt: prompt,
    });

    const params = {
        headers: {
            'Content-Type': 'application/json',
            'X-User-Id': userId,
        },
        tags: { endpoint: 'fastapi_sse_chat' },
        timeout: '120s',
    };

    const res = http.post(url, payload, params);

    ttfbTrend.add(res.timings.waiting);
    e2eLatencyTrend.add(res.timings.duration);

    const hasSseData = res.body && res.body.includes('data:');
    const hasStreamError = res.body && res.body.includes('data: [ERROR]');

    const isSuccessful = check(res, {
        'status is 200': (r) => r.status === 200,
        'is streaming response': () => Boolean(hasSseData),
        'no stream error payload': () => !hasStreamError,
    });

    // Always record 0 or 1 so Rate metric reflects true error percentage
    errorRate.add(!isSuccessful);

    if (hasSseData) {
        const chunkLines = res.body.split('\n').filter((line) => line.startsWith('data:'));
        chunksCounter.add(chunkLines.length);
    } else {
        console.error(`[k6 Error] Request failed for session ${sessionId}. Status: ${res.status}`);
    }

    sleep(1);
}
