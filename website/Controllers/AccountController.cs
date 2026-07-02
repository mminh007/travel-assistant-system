using System;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Http;
using Booking.Web.Models.ViewModels;
using Booking.Web.Services.Interfaces;

namespace Booking.Web.Controllers
{
    public class AccountController : Controller
    {
        private readonly IAuthService _authService;

        public AccountController(IAuthService authService)
        {
            _authService = authService;
        }

        [HttpGet]
        public IActionResult Login()
        {
            if (User.Identity != null && User.Identity.IsAuthenticated)
            {
                return RedirectToAction("Index", "Home");
            }
            return View();
        }

        [HttpPost]
        public async Task<IActionResult> Login(LoginViewModel model)
        {
            if (!ModelState.IsValid) return View(model);

            var deviceInfo = Request.Headers["User-Agent"].ToString();
            var response = await _authService.LoginAsync(model, deviceInfo);

            if (response.Success)
            {
                // Set JWT in a cookie for MVC requests
                var cookieOptions = new CookieOptions
                {
                    HttpOnly = true,
                    Expires = DateTime.UtcNow.AddMinutes(15),
                    Secure = true, // Ensure HTTPS
                    SameSite = SameSiteMode.Strict
                };
                Response.Cookies.Append("jwtToken", response.JwtToken, cookieOptions);

                // Set Refresh Token
                var refreshOptions = new CookieOptions
                {
                    HttpOnly = true,
                    Expires = DateTime.UtcNow.AddDays(7),
                    Secure = true,
                    SameSite = SameSiteMode.Strict
                };
                Response.Cookies.Append("refreshToken", response.RefreshToken, refreshOptions);

                return RedirectToAction("Index", "Home");
            }

            ModelState.AddModelError(string.Empty, response.Message);
            return View(model);
        }

        [HttpGet]
        public IActionResult Register()
        {
            if (User.Identity != null && User.Identity.IsAuthenticated)
            {
                return RedirectToAction("Index", "Home");
            }
            return View();
        }

        [HttpPost]
        public async Task<IActionResult> Register(RegisterViewModel model)
        {
            if (!ModelState.IsValid) return View(model);

            var deviceInfo = Request.Headers["User-Agent"].ToString();
            var response = await _authService.RegisterAsync(model, deviceInfo);

            if (response.Success)
            {
                var cookieOptions = new CookieOptions { HttpOnly = true, Expires = DateTime.UtcNow.AddMinutes(15), Secure = true };
                Response.Cookies.Append("jwtToken", response.JwtToken, cookieOptions);

                var refreshOptions = new CookieOptions { HttpOnly = true, Expires = DateTime.UtcNow.AddDays(7), Secure = true };
                Response.Cookies.Append("refreshToken", response.RefreshToken, refreshOptions);

                return RedirectToAction("Index", "Home");
            }

            ModelState.AddModelError(string.Empty, response.Message);
            return View(model);
        }

        [HttpPost]
        public async Task<IActionResult> Logout()
        {
            var refreshToken = Request.Cookies["refreshToken"];
            if (!string.IsNullOrEmpty(refreshToken))
            {
                await _authService.LogoutAsync(refreshToken);
            }

            Response.Cookies.Delete("jwtToken");
            Response.Cookies.Delete("refreshToken");

            return RedirectToAction("Index", "Home");
        }
    }
}
