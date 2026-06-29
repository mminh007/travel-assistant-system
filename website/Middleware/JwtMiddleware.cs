using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Booking.Web.Services;
using System.Linq;

namespace Booking.Web.Middleware
{
    public class JwtMiddleware
    {
        private readonly RequestDelegate _next;

        public JwtMiddleware(RequestDelegate next)
        {
            _next = next;
        }

        public async Task Invoke(HttpContext context)
        {
            // If the request contains a JWT in the Authorization header, it will be validated by JwtBearer authentication.
            // If we are using HttpOnly cookies for RefreshToken, we might need to handle token refresh here if the JWT is expired.
            // But for a simple MVC app, we often just check the cookie. Let's keep it simple: 
            // If the user has a valid JWT, they are authenticated.

            var token = context.Request.Headers["Authorization"].FirstOrDefault()?.Split(" ").Last();

            // If we store JWT in a cookie for MVC views instead of headers
            if (string.IsNullOrEmpty(token))
            {
                token = context.Request.Cookies["jwtToken"];
                if (!string.IsNullOrEmpty(token))
                {
                    context.Request.Headers.Append("Authorization", "Bearer " + token);
                }
            }

            await _next(context);
        }
    }
}
