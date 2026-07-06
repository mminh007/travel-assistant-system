using Microsoft.AspNetCore.Mvc;
using Booking.Web.Data;
using Microsoft.EntityFrameworkCore;
using Booking.Web.Models.Domain;
using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Stripe.Checkout;
using Stripe;
using Booking.Web.Services.Interfaces;
using Booking.Web.Models.DTOs;

namespace Booking.Web.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class PaymentController : ControllerBase
    {
        private readonly IBookingService _bookingService;
        private readonly IConfiguration _configuration;

        public PaymentController(IBookingService bookingService, IConfiguration configuration)
        {
            _bookingService = bookingService;
            _configuration = configuration;
        }

        [HttpPost("create-checkout-session")]
        [Authorize]
        public async Task<IActionResult> CreateCheckoutSession([FromBody] CreateCheckoutRequest request)
        {
            var userIdString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (!Guid.TryParse(userIdString, out var userId))
            {
                return Unauthorized();
            }

            var roomType = await _bookingService.GetRoomTypeWithHotelAsync(request.RoomTypeId);

            if (roomType == null)
            {
                return NotFound("Room type not found.");
            }

            var nights = (request.CheckOut - request.CheckIn).Days;
            if (nights <= 0) nights = 1;

            var totalPrice = roomType.PricePerNight * nights;

            // Create a pending booking record
            var booking = await _bookingService.CreatePendingBookingAsync(
                userId,
                roomType.Id,
                roomType.HotelId,
                request.CheckIn,
                request.CheckOut,
                nights,
                request.Guests,
                totalPrice,
                request.GuestName,
                request.GuestEmail,
                request.PhoneNumber,
                request.SpecialRequests
            );

            var domain = $"{Request.Scheme}://{Request.Host}";
            var options = new SessionCreateOptions
            {
                PaymentMethodTypes = new List<string> { "card" },
                UiMode = "embedded_page",
                ReturnUrl = $"{domain}/Booking/Success?session_id={{CHECKOUT_SESSION_ID}}",
                LineItems = new List<SessionLineItemOptions>
                {
                    new SessionLineItemOptions
                    {
                        PriceData = new SessionLineItemPriceDataOptions
                        {
                            UnitAmount = (long)(totalPrice), // Assuming VND, otherwise multiply by 100 for cents
                            Currency = "vnd",
                            ProductData = new SessionLineItemPriceDataProductDataOptions
                            {
                                Name = $"{roomType.Hotel.Name} - {roomType.Name}",
                                Description = $"{nights} night(s) from {request.CheckIn:yyyy-MM-dd} to {request.CheckOut:yyyy-MM-dd}"
                            },
                        },
                        Quantity = 1,
                    },
                },
                Mode = "payment",
                ClientReferenceId = booking.Id.ToString(),
            };

            var service = new SessionService();
            Session session = service.Create(options);

            return Ok(new { clientSecret = session.ClientSecret });
        }
        
        [HttpPost("pay-pending-booking/{id}")]
        [Authorize]
        public async Task<IActionResult> PayPendingBooking(Guid id)
        {
            var userIdString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (!Guid.TryParse(userIdString, out var userId))
            {
                return Unauthorized();
            }

            var _dbContext = HttpContext.RequestServices.GetRequiredService<AppDbContext>();
            var booking = await _dbContext.Bookings
                .Include(b => b.RoomType)
                .ThenInclude(rt => rt.Hotel)
                .FirstOrDefaultAsync(b => b.Id == id && b.UserId == userId);

            if (booking == null || booking.Status != "Pending")
            {
                return NotFound("Booking not found or not in pending state.");
            }

            var domain = $"{Request.Scheme}://{Request.Host}";
            var options = new SessionCreateOptions
            {
                PaymentMethodTypes = new List<string> { "card" },
                UiMode = "hosted_page",
                SuccessUrl = $"{domain}/Booking/Success?session_id={{CHECKOUT_SESSION_ID}}",
                CancelUrl = $"{domain}/UserProfile/HistoryBooking",
                LineItems = new List<SessionLineItemOptions>
                {
                    new SessionLineItemOptions
                    {
                        PriceData = new SessionLineItemPriceDataOptions
                        {
                            UnitAmount = (long)(booking.TotalPrice),
                            Currency = "vnd",
                            ProductData = new SessionLineItemPriceDataProductDataOptions
                            {
                                Name = $"{booking.RoomType.Hotel.Name} - {booking.RoomType.Name}",
                                Description = $"{booking.TotalNights} night(s) from {booking.CheckInDate:yyyy-MM-dd} to {booking.CheckOutDate:yyyy-MM-dd}"
                            },
                        },
                        Quantity = 1,
                    },
                },
                Mode = "payment",
                ClientReferenceId = booking.Id.ToString(),
            };

            var service = new SessionService();
            Session session = service.Create(options);

            return Ok(new { url = session.Url });
        }
        
        [HttpPost("webhook")]
        public async Task<IActionResult> Webhook()
        {
            var json = await new StreamReader(HttpContext.Request.Body).ReadToEndAsync();
            var endpointSecret = _configuration["StripeSettings:WebhookSecret"];

            try
            {
                var stripeEvent = EventUtility.ConstructEvent(json,
                    Request.Headers["Stripe-Signature"], endpointSecret);

                if (stripeEvent.Type == "checkout.session.completed")
                {
                    var session = stripeEvent.Data.Object as Session;

                    if (session != null && Guid.TryParse(session.ClientReferenceId, out var bookingId))
                    {
                        var amount = session.AmountTotal.HasValue ? session.AmountTotal.Value / 100m : 0m;
                        await _bookingService.ConfirmBookingAndRecordPaymentAsync(
                            bookingId,
                            session.Currency,
                            session.PaymentIntentId ?? session.Id,
                            amount
                        );
                    }
                }
                return Ok();
            }
            catch (StripeException e)
            {
                return BadRequest(e.Message);
            }
        }
    }

}
