using Microsoft.AspNetCore.SignalR;
using AgentApp.Protos;
using Grpc.Core;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Authorization;
using System.Threading;
using System;
using Microsoft.AspNetCore.Http;

namespace Booking.Web.Hubs
{
    [Authorize]
    public class ChatHub : Hub
    {
        private readonly AgentService.AgentServiceClient _agentClient;

        public ChatHub(AgentService.AgentServiceClient agentClient)
        {
            _agentClient = agentClient;
        }

        public async Task SendMessage(string message)
        {
            if (string.IsNullOrWhiteSpace(message)) return;

            var userId = Context.UserIdentifier ?? "UnknownUser";
            // We use ConnectionId as the session for the chat
            var sessionId = Context.ConnectionId;

            // Extract CorrelationId from HttpContext items if available
            var httpContext = Context.GetHttpContext();
            var correlationId = httpContext?.Items["X-Correlation-ID"]?.ToString() ?? Guid.NewGuid().ToString();

            var request = new ChatRequest
            {
                UserId = userId,
                SessionId = sessionId,
                Prompt = message
            };

            var headers = new Metadata
            {
                { "x-correlation-id", correlationId }
            };

            try
            {
                using var call = _agentClient.StreamChat(request, headers);

                await foreach (var response in call.ResponseStream.ReadAllAsync())
                {
                    if (!string.IsNullOrEmpty(response.Chunk))
                    {
                        await Clients.Caller.SendAsync("ReceiveMessageChunk", response.Chunk);
                    }
                }
                // Send a signal that the stream has finished
                await Clients.Caller.SendAsync("ReceiveStreamComplete");
            }
            catch (RpcException ex)
            {
                await Clients.Caller.SendAsync("ReceiveMessageChunk", $"\n**Error connecting to Agent:** {ex.Status.Detail}");
                await Clients.Caller.SendAsync("ReceiveStreamComplete");
            }
            catch (Exception ex)
            {
                await Clients.Caller.SendAsync("ReceiveMessageChunk", $"\n**An error occurred:** {ex.Message}");
                await Clients.Caller.SendAsync("ReceiveStreamComplete");
            }
        }
    }
}
