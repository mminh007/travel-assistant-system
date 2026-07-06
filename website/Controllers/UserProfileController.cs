using Microsoft.AspNetCore.Mvc;
using Booking.Web.Data;
using Microsoft.EntityFrameworkCore;
using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Booking.Web.Services.Interfaces;
using Booking.Web.Models.DTOs;

namespace Booking.Web.Controllers
{
    [Authorize]
    public class UserProfileController : Controller
    {
        private readonly AppDbContext _context;
        private readonly IBookingService _bookingService;

        public UserProfileController(AppDbContext context, IBookingService bookingService)
        {
            _context = context;
            _bookingService = bookingService;
        }

        [HttpGet]
        public async Task<IActionResult> UserInfo()
        {
            var userIdString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (!Guid.TryParse(userIdString, out var userId))
            {
                return RedirectToAction("Login", "Account");
            }

            var user = await _context.Users.FirstOrDefaultAsync(u => u.Id == userId);
            if (user == null)
            {
                return NotFound();
            }

            return View(user);
        }

        [HttpGet]
        public async Task<IActionResult> HistoryBooking()
        {
            var userIdString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (!Guid.TryParse(userIdString, out var userId))
            {
                return RedirectToAction("Login", "Account");
            }

            var bookings = await _bookingService.GetBookingsByUserIdAsync(userId);
            return View(bookings);
        }

        [HttpPost]
        [Route("api/user/update-info")]
        public async Task<IActionResult> UpdateInfo([FromBody] UpdateUserInfoRequest request)
        {
            var userIdString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (!Guid.TryParse(userIdString, out var userId))
            {
                return Unauthorized();
            }

            var user = await _context.Users.FirstOrDefaultAsync(u => u.Id == userId);
            if (user == null)
            {
                return NotFound();
            }

            user.FullName = request.FullName ?? "";
            user.PhoneNumber = request.PhoneNumber ?? "";
            user.Address = request.Address ?? "";
            user.Nationality = request.Nationality ?? "";
            user.UpdatedAt = DateTime.UtcNow;

            _context.Users.Update(user);
            await _context.SaveChangesAsync();

            return Ok(new { success = true });
        }

        [HttpPost]
        [Route("api/booking/cancel/{id}")]
        public async Task<IActionResult> CancelBooking(Guid id)
        {
            var userIdString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (!Guid.TryParse(userIdString, out var userId))
            {
                return Unauthorized();
            }

            var result = await _bookingService.CancelBookingAsync(id, userId);
            if (result)
            {
                return Ok(new { success = true });
            }

            return BadRequest(new { success = false, message = "Cannot cancel this booking." });
        }
    }
}
