// load_tests/travel_perf_test.js
// ============================================================
// Travel Assistant System — Comprehensive Performance Test
// Covers: 10 → 50 → 100 → 200 VU ramp & 300, 500, 700, 1000 VU stress profiles
// Supports: CACHE_MODE, COMPLEXITY_FILTER, STAGE_PROFILE env vars
// Pushes custom metrics to Prometheus via Remote Write
// ============================================================
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter, Gauge } from 'k6/metrics';
import { SharedArray } from 'k6/data';

// ─── CUSTOM METRICS ──────────────────────────────────────────
// End-to-end latency per complexity tier
const e2eLatencyLow    = new Trend('travel_e2e_ms_low',    true);
const e2eLatencyMedium = new Trend('travel_e2e_ms_medium', true);
const e2eLatencyHigh   = new Trend('travel_e2e_ms_high',   true);
const e2eLatencyAll    = new Trend('travel_e2e_ms_all',    true);

// Time To First Byte (proxy for TTFT via SSE)
const ttfbLow    = new Trend('travel_ttfb_ms_low',    true);
const ttfbMedium = new Trend('travel_ttfb_ms_medium', true);
const ttfbHigh   = new Trend('travel_ttfb_ms_high',   true);
const ttfbAll    = new Trend('travel_ttfb_ms_all',    true);

// Error & success tracking
const errorRate       = new Rate('travel_error_rate');
const cacheHitRate    = new Rate('travel_cache_hit_rate');
const sseChunksTotal  = new Counter('travel_sse_chunks_total');

// Throughput
const requestsPerComplexity = {
    low:    new Counter('travel_requests_low_total'),
    medium: new Counter('travel_requests_medium_total'),
    high:   new Counter('travel_requests_high_total'),
};

// ─── CONFIGURATION ──────────────────────────────────────────
const BASE_URL       = __ENV.AGENT_HTTP_URL   || 'http://agent_api:8080';
const CACHE_MODE     = __ENV.CACHE_MODE       || 'unique';   // 'unique' | 'mixed'
const COMPLEXITY_FILTER = __ENV.COMPLEXITY_FILTER || 'all'; // 'all' | 'low' | 'medium' | 'high'
const STAGE_PROFILE  = __ENV.STAGE_PROFILE    || 'stepup';  // 'stepup' | 'stepup_heavy' | 'stress_300' | 'stress_500' | 'stress_700' | 'stress_1000' | 'soak' | 'spike' | 'smoke'

// ─── LOAD QUESTION DATABASE ─────────────────────────────────
const ALL_QUESTIONS = new SharedArray('questions', function () {
    const raw = open('./questions_db.json');
    const db  = JSON.parse(raw);
    return db.questions;
});

// Pre-segment by complexity for weighted selection
const QUESTIONS_BY_COMPLEXITY = {
    low:    ALL_QUESTIONS.filter(q => q.complexity === 'low'),
    medium: ALL_QUESTIONS.filter(q => q.complexity === 'medium'),
    high:   ALL_QUESTIONS.filter(q => q.complexity === 'high'),
};

// ─── STAGE PROFILES ──────────────────────────────────────────
const STAGE_PROFILES = {
    // 🎯 Main target: 10 → 50 → 100 → 200 VU step-up (~17m)
    stepup: [
        { duration: '2m',  target: 10  },  // Stage 1: Baseline / warm-up (10 VUs)
        { duration: '1m',  target: 10  },  // Hold at 10 for stable baseline
        { duration: '3m',  target: 50  },  // Stage 2: Normal load (50 VUs)
        { duration: '1m',  target: 50  },  // Hold at 50
        { duration: '3m',  target: 100 },  // Stage 3: High load — tests vLLM continuous batching
        { duration: '1m',  target: 100 },  // Hold at 100
        { duration: '3m',  target: 200 },  // Stage 4: Stress — monitors queue + preemptions
        { duration: '1m',  target: 200 },  // Hold at 200
        { duration: '2m',  target: 0   },  // Cool-down
    ],
    // 🚀 Extreme Step-up: 300 → 500 → 700 → 1000 VU step-up (~18m)
    stepup_heavy: [
        { duration: '2m',  target: 300  },  // Stage 1: Ramp to 300 VUs
        { duration: '2m',  target: 300  },  // Hold at 300 VUs
        { duration: '2m',  target: 500  },  // Stage 2: Ramp to 500 VUs
        { duration: '2m',  target: 500  },  // Hold at 500 VUs
        { duration: '2m',  target: 700  },  // Stage 3: Ramp to 700 VUs
        { duration: '2m',  target: 700  },  // Hold at 700 VUs
        { duration: '2m',  target: 1000 },  // Stage 4: Peak stress to 1000 VUs
        { duration: '2m',  target: 1000 },  // Hold at 1000 VUs
        { duration: '2m',  target: 0    },  // Cool-down
    ],
    // 💥 Dedicated Cases: 300, 500, 700, 1000 Concurrent Users (VUs)
    // 300 VUs Concurrent Load (~6m)
    stress_300: [
        { duration: '1m30s', target: 300 },  // Ramp-up to 300 VUs
        { duration: '3m30s', target: 300 },  // Sustained 300 concurrent users
        { duration: '1m',    target: 0   },  // Cool-down
    ],
    // 500 VUs Concurrent Load (~7m)
    stress_500: [
        { duration: '2m',    target: 500 },  // Ramp-up to 500 VUs
        { duration: '4m',    target: 500 },  // Sustained 500 concurrent users
        { duration: '1m',    target: 0   },  // Cool-down
    ],
    // 700 VUs Concurrent Load (~8m)
    stress_700: [
        { duration: '2m30s', target: 700 },  // Ramp-up to 700 VUs
        { duration: '4m',    target: 700 },  // Sustained 700 concurrent users
        { duration: '1m30s', target: 0   },  // Cool-down
    ],
    // 1000 VUs Concurrent Load (~9m)
    stress_1000: [
        { duration: '3m',    target: 1000 }, // Ramp-up to 1000 VUs
        { duration: '4m',    target: 1000 }, // Sustained 1000 concurrent users
        { duration: '2m',    target: 0    }, // Cool-down
    ],
    // 30-minute sustained load at 50 VUs — detect memory leaks, Redis OOM
    soak: [
        { duration: '2m',  target: 50  },
        { duration: '26m', target: 50  },
        { duration: '2m',  target: 0   },
    ],
    // Spike: instant ramp to 200 VUs — test auto-recovery
    spike: [
        { duration: '30s', target: 5   },   // Minimal warm-up
        { duration: '10s', target: 200 },   // Spike!
        { duration: '3m',  target: 200 },   // Hold spike
        { duration: '30s', target: 5   },   // Recover
        { duration: '1m',  target: 0   },
    ],
    // Quick smoke — verify system before real test
    smoke: [
        { duration: '1m',  target: 3   },
        { duration: '30s', target: 0   },
    ],
};

// Aliases for convenient CLI usage (-e STAGE_PROFILE=300 / 500 / 700 / 1000 or vu300 / vu500 / vu700 / vu1000)
STAGE_PROFILES['300']          = STAGE_PROFILES.stress_300;
STAGE_PROFILES['vu300']        = STAGE_PROFILES.stress_300;
STAGE_PROFILES['vu_300']       = STAGE_PROFILES.stress_300;

STAGE_PROFILES['500']          = STAGE_PROFILES.stress_500;
STAGE_PROFILES['vu500']        = STAGE_PROFILES.stress_500;
STAGE_PROFILES['vu_500']       = STAGE_PROFILES.stress_500;

STAGE_PROFILES['700']          = STAGE_PROFILES.stress_700;
STAGE_PROFILES['vu700']        = STAGE_PROFILES.stress_700;
STAGE_PROFILES['vu_700']       = STAGE_PROFILES.stress_700;

STAGE_PROFILES['1000']         = STAGE_PROFILES.stress_1000;
STAGE_PROFILES['vu1000']       = STAGE_PROFILES.stress_1000;
STAGE_PROFILES['vu_1000']      = STAGE_PROFILES.stress_1000;

STAGE_PROFILES['stepup_1k']    = STAGE_PROFILES.stepup_heavy;
STAGE_PROFILES['stepup_1000']  = STAGE_PROFILES.stepup_heavy;

// ─── THRESHOLDS ──────────────────────────────────────────────
export const options = {
    stages: STAGE_PROFILES[STAGE_PROFILE] || STAGE_PROFILES.stepup,

    thresholds: {
        // HTTP-level
        http_req_failed:          ['rate<0.02'],       // < 2% HTTP failures overall

        // Custom — global
        travel_error_rate:        ['rate<0.05'],       // < 5% application-level errors
        travel_e2e_ms_all:        ['p(95)<40000'],     // P95 under 40s (all tiers combined)

        // Tier-specific SLA
        travel_e2e_ms_low:        ['p(50)<3000', 'p(95)<8000'],    // Simple queries must be fast
        travel_e2e_ms_medium:     ['p(50)<8000', 'p(95)<20000'],   // Multi-step planning
        travel_e2e_ms_high:       ['p(95)<40000'],                 // Complex: full pipeline

        // TTFB (Time to First Byte → proxy for TTFT)
        travel_ttfb_ms_low:       ['p(95)<2000'],
        travel_ttfb_ms_medium:    ['p(95)<5000'],
        travel_ttfb_ms_high:      ['p(95)<10000'],
    },

    // k6 → Prometheus Remote Write (set via env in docker-compose)
    // K6_PROMETHEUS_RW_SERVER_URL and K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM
    // are injected by docker-compose environment section.

    tags: {
        test_profile: STAGE_PROFILE,
        cache_mode:   CACHE_MODE,
    },
};

// ─── HELPERS ─────────────────────────────────────────────────

/**
 * Weighted random complexity selection.
 * Low: 40%, Medium: 40%, High: 20%
 * In COMPLEXITY_FILTER mode: only returns filtered tier.
 */
function pickComplexity() {
    if (COMPLEXITY_FILTER !== 'all') return COMPLEXITY_FILTER;
    const r = Math.random();
    if (r < 0.40) return 'low';
    if (r < 0.80) return 'medium';
    return 'high';
}

/**
 * Pick a question for the given complexity.
 * In 'unique' mode: appends a unique cache-bypass tag.
 * In 'mixed' mode: 30% of requests use canonical prompts (cache hit possible).
 */
function pickQuestion(complexity, vu, iter) {
    const pool   = QUESTIONS_BY_COMPLEXITY[complexity];
    const idx    = (vu + iter) % pool.length;
    const q      = pool[idx];

    const bypassCache = (CACHE_MODE === 'unique') || (iter % 3 !== 0);
    const prompt = bypassCache
        ? `${q.prompt} [ref:${vu}-${iter}]`
        : q.prompt;

    return { prompt, question: q };
}

/**
 * Record metric by complexity tier.
 */
function recordMetrics(complexity, durationMs, ttfbMs, isError, isCacheHit, chunkCount) {
    // Trend by tier
    const trendMap = { low: e2eLatencyLow, medium: e2eLatencyMedium, high: e2eLatencyHigh };
    const ttfbMap  = { low: ttfbLow,       medium: ttfbMedium,       high: ttfbHigh       };
    trendMap[complexity].add(durationMs);
    ttfbMap[complexity].add(ttfbMs);

    // Global trends
    e2eLatencyAll.add(durationMs);
    ttfbAll.add(ttfbMs);

    // Rates & counters
    errorRate.add(isError ? 1 : 0);
    cacheHitRate.add(isCacheHit ? 1 : 0);
    sseChunksTotal.add(chunkCount);
    requestsPerComplexity[complexity].add(1);
}

// ─── MAIN VU FUNCTION ────────────────────────────────────────
export default function () {
    const vu   = __VU;
    const iter = __ITER;

    // Each VU uses an anonymous identity that won't pollute Redis checkpointer
    const userId    = `anon_perf_${vu}`;
    const sessionId = `perf_${STAGE_PROFILE}_${vu}_${iter}`;

    // Select complexity and question
    const complexity          = pickComplexity();
    const { prompt, question } = pickQuestion(complexity, vu, iter);

    const payload = JSON.stringify({
        user_id:    userId,
        session_id: sessionId,
        prompt:     prompt,
    });

    const params = {
        headers: {
            'Content-Type': 'application/json',
            'X-User-Id':    userId,
        },
        tags: {
            endpoint:   'sse_chat',
            complexity: complexity,
            intent:     question.intent_category,
            question_id: question.id,
        },
        timeout: '300s',
    };

    const res = http.post(`${BASE_URL}/api/chat/stream`, payload, params);

    // ── Parse SSE response ──
    const body          = res.body || '';
    const hasSseData    = body.includes('data:');
    const hasStreamError = body.includes('data: [ERROR]');
    const isCacheHit    = body.includes('"cache_hit":true') || body.includes('"source":"cache"');
    const chunkLines    = hasSseData
        ? body.split('\n').filter(l => l.startsWith('data:'))
        : [];

    // ── Assertions ──
    const isSuccess = check(res, {
        'status 200':            (r) => r.status === 200,
        'has SSE data':          () => hasSseData,
        'no stream error':       () => !hasStreamError,
        [`complexity=${complexity}`]: () => true,  // tag for Grafana filtering
    });

    const isError = !isSuccess || hasStreamError;

    // ── Record all metrics ──
    recordMetrics(
        complexity,
        res.timings.duration,
        res.timings.waiting,   // TTFB = time waiting for first byte
        isError,
        isCacheHit,
        chunkLines.length,
    );

    if (isError) {
        console.error(
            `[PERF ERROR] VU=${vu} ITER=${iter} session=${sessionId} ` +
            `complexity=${complexity} status=${res.status} ` +
            `body_preview=${body.slice(0, 200)}`
        );
    }

    // Realistic think time between requests
    // Low: shorter think time (fast FAQ-style), High: longer (user reading response)
    const thinkTime = { low: 1, medium: 2, high: 3 }[complexity] || 1;
    sleep(thinkTime);
}

// ─── SETUP (runs once before VUs start) ─────────────────────
export function setup() {
    console.log(`
╔══════════════════════════════════════════════════════════╗
║     Travel Assistant — Performance Test Starting         ║
╠══════════════════════════════════════════════════════════╣
║  Stage Profile  : ${STAGE_PROFILE.padEnd(38)}║
║  Cache Mode     : ${CACHE_MODE.padEnd(38)}║
║  Complexity     : ${COMPLEXITY_FILTER.padEnd(38)}║
║  Target URL     : ${BASE_URL.padEnd(38)}║
║  Questions DB   : ${ALL_QUESTIONS.length} questions loaded${' '.repeat(Math.max(0, 18 - String(ALL_QUESTIONS.length).length))}║
║    LOW          : ${QUESTIONS_BY_COMPLEXITY.low.length} questions${' '.repeat(Math.max(0, 30 - String(QUESTIONS_BY_COMPLEXITY.low.length).length))}║
║    MEDIUM       : ${QUESTIONS_BY_COMPLEXITY.medium.length} questions${' '.repeat(Math.max(0, 30 - String(QUESTIONS_BY_COMPLEXITY.medium.length).length))}║
║    HIGH         : ${QUESTIONS_BY_COMPLEXITY.high.length} questions${' '.repeat(Math.max(0, 30 - String(QUESTIONS_BY_COMPLEXITY.high.length).length))}║
╚══════════════════════════════════════════════════════════╝
    `);

    // Quick connectivity check
    const probe = http.get(`${BASE_URL}/docs`, { timeout: '10s' });
    if (probe.status !== 200) {
        console.warn(`[SETUP WARNING] Agent API health check returned ${probe.status}. Proceeding anyway.`);
    } else {
        console.log(`[SETUP] Agent API reachable at ${BASE_URL} ✅`);
    }
}

// ─── TEARDOWN (runs once after all VUs finish) ───────────────
export function teardown(data) {
    console.log(`
╔══════════════════════════════════════════════════════════╗
║     Travel Assistant — HTTP Test Complete                ║
╠══════════════════════════════════════════════════════════╣
║  Check Grafana at http://localhost:3001 for dashboards   ║
║  Check Prometheus at http://localhost:9090 for metrics   ║
║  Report files generated in agent/load_tests/reports/:    ║
║    - http_test_<datetime>.html (Interactive report)      ║
║    - http_test_<datetime>.json (Machine-readable)        ║
║    - latest_http_test.html                               ║
╚══════════════════════════════════════════════════════════╝
    `);
}

function getFormattedTimestamp() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const yyyy = d.getFullYear();
    const mm = pad(d.getMonth() + 1);
    const dd = pad(d.getDate());
    const hh = pad(d.getHours());
    const min = pad(d.getMinutes());
    const ss = pad(d.getSeconds());
    return `${yyyy}${mm}${dd}_${hh}${min}${ss}`;
}

// ─── AUTOMATED HTML & JSON REPORT GENERATION ────────────────
function formatMs(val) {
    if (val === undefined || val === null) return 'N/A';
    if (val < 1000) return `${val.toFixed(1)} ms`;
    return `${(val / 1000).toFixed(2)} s`;
}

function getVal(metric, key, fallback = 0) {
    if (!metric || !metric.values) return fallback;
    return metric.values[key] !== undefined ? metric.values[key] : fallback;
}

function generateHtmlReport(data) {
    const m = data.metrics || {};
    const totalReqs = getVal(m.http_reqs, 'count', 0);
    const rps = getVal(m.http_reqs, 'rate', 0).toFixed(2);
    const errRate = (getVal(m.travel_error_rate, 'rate', 0) * 100).toFixed(2);
    const cacheHit = (getVal(m.travel_cache_hit_rate, 'rate', 0) * 100).toFixed(2);
    const totalChunks = getVal(m.travel_sse_chunks_total, 'count', 0);
    const now = new Date().toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });

    const tiers = [
        { label: 'Low (Simple / FAQ / Quick Hotel)', key: 'travel_e2e_ms_low', ttfb: 'travel_ttfb_ms_low', countKey: 'travel_requests_low_total' },
        { label: 'Medium (Itinerary / Comparison)', key: 'travel_e2e_ms_medium', ttfb: 'travel_ttfb_ms_medium', countKey: 'travel_requests_medium_total' },
        { label: 'High (Complex / Multi-city / Budget)', key: 'travel_e2e_ms_high', ttfb: 'travel_ttfb_ms_high', countKey: 'travel_requests_high_total' },
        { label: 'Total (All Queries Combined)', key: 'travel_e2e_ms_all', ttfb: 'travel_ttfb_ms_all', countKey: null },
    ];

    let latencyRows = '';
    for (const t of tiers) {
        const metric = m[t.key];
        const ttfbMetric = m[t.ttfb];
        const count = t.countKey ? getVal(m[t.countKey], 'count', 0) : totalReqs;
        latencyRows += `
        <tr>
            <td><strong>${t.label}</strong></td>
            <td style="text-align: center;">${count}</td>
            <td style="text-align: right;">${formatMs(getVal(metric, 'med'))}</td>
            <td style="text-align: right;">${formatMs(getVal(metric, 'p(90)'))}</td>
            <td style="text-align: right; color: #2563eb; font-weight: bold;">${formatMs(getVal(metric, 'p(95)'))}</td>
            <td style="text-align: right;">${formatMs(getVal(metric, 'avg'))}</td>
            <td style="text-align: right;">${formatMs(getVal(ttfbMetric, 'p(95)'))}</td>
        </tr>`;
    }

    let thresholdRows = '';
    for (const [metricName, obj] of Object.entries(m)) {
        if (obj.thresholds) {
            for (const [thName, thObj] of Object.entries(obj.thresholds)) {
                const passed = thObj.ok;
                const statusBadge = passed
                    ? '<span class="badge pass">PASSED</span>'
                    : '<span class="badge fail">FAILED</span>';
                thresholdRows += `
                <tr>
                    <td><code>${metricName}</code></td>
                    <td>${thName}</td>
                    <td style="text-align: center;">${statusBadge}</td>
                </tr>`;
            }
        }
    }

    return `<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo Cáo Hiệu Năng — Travel Assistant System</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 24px; line-height: 1.5; }
        .container { max-width: 1100px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); padding: 32px; }
        h1 { margin-top: 0; color: #0f172a; font-size: 24px; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; }
        .meta { color: #64748b; font-size: 14px; margin-bottom: 24px; display: flex; flex-wrap: wrap; gap: 12px; }
        .meta-item { background: #f1f5f9; padding: 6px 12px; border-radius: 6px; }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
        .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; text-align: center; }
        .card-val { font-size: 26px; font-weight: 700; color: #0f172a; margin-top: 6px; }
        .card-label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
        h2 { font-size: 18px; color: #334155; margin-top: 28px; margin-bottom: 14px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
        th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f8fafc; color: #475569; font-weight: 600; }
        tr:hover { background: #f8fafc; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .badge.pass { background: #dcfce7; color: #166534; }
        .badge.fail { background: #fee2e2; color: #991b1b; }
        .footer { margin-top: 32px; font-size: 13px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 16px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Báo Cáo Hiệu Năng & Khả Năng Chịu Tải (Performance Report)</h1>
        <div class="meta">
            <div class="meta-item">⏱️ Thời gian test: <strong>${now}</strong></div>
            <div class="meta-item">🎯 Profile kịch bản: <strong>${__ENV.STAGE_PROFILE || 'stepup'}</strong></div>
            <div class="meta-item">⚡ Cache Mode: <strong>${__ENV.CACHE_MODE || 'unique'}</strong></div>
            <div class="meta-item">🌐 Endpoint: <strong>${__ENV.AGENT_HTTP_URL || 'http://agent_api:8080'}</strong></div>
        </div>

        <div class="cards">
            <div class="card">
                <div class="card-label">Tổng Requests</div>
                <div class="card-val">${totalReqs}</div>
            </div>
            <div class="card">
                <div class="card-label">Throughput (RPS)</div>
                <div class="card-val">${rps} <span style="font-size: 13px; font-weight: normal;">req/s</span></div>
            </div>
            <div class="card">
                <div class="card-label">Tỷ Lệ Lỗi (Error Rate)</div>
                <div class="card-val" style="color: ${Number(errRate) > 5 ? '#ef4444' : '#10b981'};">${errRate}%</div>
            </div>
            <div class="card">
                <div class="card-label">Semantic Cache Hit</div>
                <div class="card-val" style="color: #6366f1;">${cacheHit}%</div>
            </div>
            <div class="card">
                <div class="card-label">Tổng Chunks SSE</div>
                <div class="card-val">${totalChunks}</div>
            </div>
        </div>

        <h2>⏱️ Phân Tầng Độ Trễ Theo Độ Phức Tạp (Latency Breakdown by Tier)</h2>
        <table>
            <thead>
                <tr>
                    <th>Tầng Câu Hỏi (Complexity Tier)</th>
                    <th style="text-align: center;">Số Request</th>
                    <th style="text-align: right;">P50 (Median)</th>
                    <th style="text-align: right;">P90</th>
                    <th style="text-align: right;">P95 (SLA)</th>
                    <th style="text-align: right;">Trung Bình</th>
                    <th style="text-align: right;">TTFB P95 (First Token)</th>
                </tr>
            </thead>
            <tbody>
                ${latencyRows}
            </tbody>
        </table>

        <h2>🎯 Đánh Giá Tiêu Chuẩn SLA (Thresholds / SLAs)</h2>
        <table>
            <thead>
                <tr>
                    <th>Chỉ số (Metric)</th>
                    <th>Điều kiện cam kết SLA</th>
                    <th style="text-align: center;">Kết quả (Status)</th>
                </tr>
            </thead>
            <tbody>
                ${thresholdRows || '<tr><td colspan="3">Không có threshold được kích hoạt</td></tr>'}
            </tbody>
        </table>

        <div class="footer">
            Báo cáo được xuất tự động bởi <strong>k6 Travel Performance Test Engine</strong> — Travel Assistant System.<br/>
            Dữ liệu time-series tương ứng được lưu trữ tại Prometheus và trực quan hóa tại Grafana Dashboard.
        </div>
    </div>
</body>
</html>`;
}

export function handleSummary(data) {
    const ts = getFormattedTimestamp();
    const htmlReport = generateHtmlReport(data);
    const jsonReport = JSON.stringify(data, null, 2);

    return {
        [`/load_tests/reports/http_test_${ts}.html`]: htmlReport,
        [`/load_tests/reports/http_test_${ts}.json`]: jsonReport,
        '/load_tests/reports/latest_http_test.html': htmlReport,
        '/load_tests/reports/latest_http_test.json': jsonReport,
        '/load_tests/summary_report.html': htmlReport,
        '/load_tests/summary_report.json': jsonReport,
    };
}

