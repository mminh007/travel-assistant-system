using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using System;
using System.Text.Json;
using System.Threading.Tasks;

namespace Booking.Web.Middleware
{
    public class GlobalExceptionMiddleware
    {
        private readonly RequestDelegate _next;
        private readonly ILogger<GlobalExceptionMiddleware> _logger;

        public GlobalExceptionMiddleware(RequestDelegate next, ILogger<GlobalExceptionMiddleware> logger)
        {
            _next = next;
            _logger = logger;
        }

        public async Task InvokeAsync(HttpContext context)
        {
            try
            {
                await _next(context);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "An unhandled exception has occurred.");
                await HandleExceptionAsync(context, ex);
            }
        }

        private static Task HandleExceptionAsync(HttpContext context, Exception exception)
        {
            var isApiRequest = context.Request.Path.StartsWithSegments("/api");

            if (isApiRequest)
            {
                context.Response.ContentType = "application/json";
                context.Response.StatusCode = StatusCodes.Status500InternalServerError;

                var correlationId = context.Items.TryGetValue("X-Correlation-ID", out var id) ? id?.ToString() : "N/A";

                var response = new
                {
                    error = "Internal Server Error from the custom middleware.",
                    message = exception.Message, // Ideally we wouldn't expose raw exception in production
                    correlationId = correlationId
                };

                return context.Response.WriteAsync(JsonSerializer.Serialize(response));
            }
            else
            {
                // For non-API requests, redirect to error page (preserving original MVC behavior if needed)
                context.Response.Redirect("/Home/Error");
                return Task.CompletedTask;
            }
        }
    }
}
