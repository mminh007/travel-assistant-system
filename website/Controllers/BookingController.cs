using Microsoft.AspNetCore.Mvc;
using Booking.Web.Models.Domain;
using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Booking.Web.Services.Interfaces;

namespace Booking.Web.Controllers
{
    [Authorize]
    public class BookingController : Controller
    {
        private readonly IBookingService _bookingService;
        private readonly IConfiguration _configuration;

        public BookingController(IBookingService bookingService, IConfiguration configuration)
        {
            _bookingService = bookingService;
            _configuration = configuration;
        }

        // Action for rendering the Confirmation Page
        [HttpGet("Booking/Confirmation")]
        public async Task<IActionResult> Confirmation([FromQuery] Guid roomTypeId, [FromQuery] string checkIn, [FromQuery] string checkOut)
        {
            var roomType = await _bookingService.GetRoomTypeWithHotelAsync(roomTypeId);

            if (roomType == null)
            {
                return NotFound();
            }

            if (!DateTime.TryParse(checkIn, out var parsedCheckIn) || !DateTime.TryParse(checkOut, out var parsedCheckOut))
            {
                // Default to tomorrow and day after if not provided correctly
                parsedCheckIn = DateTime.UtcNow.Date.AddDays(1);
                parsedCheckOut = parsedCheckIn.AddDays(1);
            }

            var nights = (parsedCheckOut - parsedCheckIn).Days;
            if (nights <= 0) nights = 1;

            var totalPrice = roomType.PricePerNight * nights;

            ViewData["CheckIn"] = parsedCheckIn.ToString("yyyy-MM-dd");
            ViewData["CheckOut"] = parsedCheckOut.ToString("yyyy-MM-dd");
            ViewData["Nights"] = nights;
            ViewData["TotalPrice"] = totalPrice;
            ViewData["StripePublishableKey"] = _configuration["StripeSettings:PublishableKey"];

            return View(roomType);
        }

        [HttpGet("Booking/Success")]
        public async Task<IActionResult> Success([FromQuery] string session_id)
        {
            // Here you can verify the session with Stripe if needed,
            // or fetch the booking record based on session_id if we stored it
            ViewData["SessionId"] = session_id;
            return View();
        }

        [HttpGet("Booking/Cancel")]
        public IActionResult Cancel()
        {
            return View();
        }
    }
}
