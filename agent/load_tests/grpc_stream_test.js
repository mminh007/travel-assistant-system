// load_tests/grpc_stream_test.js
// Server-streaming gRPC load test against AgentService/StreamChat (port 50051)
import grpc from 'k6/net/grpc';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const client = new grpc.Client();
client.load(['.'], 'chat.proto');

const grpcTtftTrend = new Trend('custom_grpc_ttft_ms', true);
const grpcE2eTrend = new Trend('custom_grpc_e2e_ms', true);
const grpcErrorRate = new Rate('custom_grpc_errors');
const grpcChunksCounter = new Counter('custom_grpc_chunks_total');

const GRPC_HOST = __ENV.AGENT_GRPC_HOST || 'agent_grpc:50051';

const BOOKING_PROMPTS = [
    "Tìm khách sạn 5 sao tại Đà Nẵng gần biển Mỹ Khê có hồ bơi.",
    "Recommend a 4-star hotel in Nha Trang under 2 million VND per night.",
    "Lập kế hoạch du lịch Phú Quốc 3 ngày 2 đêm cho 2 người.",
    "What are the best family resorts in Hoi An with free breakfast?",
];

export const options = {
    stages: [
        { duration: '15s', target: 4 },
        { duration: '30s', target: 10 },
        { duration: '15s', target: 0 },
    ],
    thresholds: {
        custom_grpc_errors: ['rate<0.05'],
        custom_grpc_e2e_ms: ['p(95)<25000'],
    },
};

let connected = false;

export default function () {
    if (!connected) {
        client.connect(GRPC_HOST, { plaintext: true });
        connected = true;
    }

    const userId = `anon_k6_grpc_${__VU}`;
    const sessionId = `grpc_session_${__VU}_${__ITER}`;
    const basePrompt = BOOKING_PROMPTS[(__VU + __ITER) % BOOKING_PROMPTS.length];
    const prompt = `${basePrompt} [grpc:${__VU}-${__ITER}]`;

    const startTs = Date.now();
    let firstChunkTs = null;
    let chunkCount = 0;
    let streamError = null;

    const ok = new Promise((resolve) => {
        const stream = new grpc.Stream(client, 'chat.AgentService/StreamChat', {
            metadata: { 'x-user-id': userId },
        });

        stream.on('data', (msg) => {
            if (msg && msg.chunk && firstChunkTs === null) {
                firstChunkTs = Date.now();
            }
            chunkCount += 1;
        });

        stream.on('error', (err) => {
            streamError = err;
            resolve(false);
        });

        stream.on('end', () => {
            resolve(streamError === null && chunkCount > 0);
        });

        stream.write({
            user_id: userId,
            session_id: sessionId,
            prompt: prompt,
        });
        stream.end();
    });

    return ok.then((success) => {
        const endTs = Date.now();
        if (firstChunkTs !== null) {
            grpcTtftTrend.add(firstChunkTs - startTs);
        }
        grpcE2eTrend.add(endTs - startTs);
        grpcChunksCounter.add(chunkCount);

        check(success, {
            'gRPC stream succeeded with chunks': (s) => s === true,
        });
        grpcErrorRate.add(!success);
        sleep(1);
    });
}
