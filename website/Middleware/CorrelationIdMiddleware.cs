using Microsoft.AspNetCore.Http;
using System;
using System.Threading.Tasks;

namespace Booking.Web.Middleware
{
    public class CorrelationIdMiddleware
    {
        private readonly RequestDelegate _next;
        private const string CorrelationIdHeader = "X-Correlation-ID";

        public CorrelationIdMiddleware(RequestDelegate next)
        {
            _next = next;
        }

        public async Task InvokeAsync(HttpContext context)
        {
            var correlationId = GetOrGenerateCorrelationId(context);

            context.Items[CorrelationIdHeader] = correlationId;

            context.Response.OnStarting(() =>
            {
                if (!context.Response.Headers.ContainsKey(CorrelationIdHeader))
                {
                    context.Response.Headers.Append(CorrelationIdHeader, correlationId);
                }
                return Task.CompletedTask;
            });

            await _next(context);
        }

        private string GetOrGenerateCorrelationId(HttpContext context)
        {
            if (context.Request.Headers.TryGetValue(CorrelationIdHeader, out var existingId))
            {
                return existingId.ToString();
            }

            return Guid.NewGuid().ToString();
        }
    }
}
