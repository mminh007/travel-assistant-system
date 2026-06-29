using Booking.Web.Models.DTOs;
using Booking.Web.Services;
using Microsoft.AspNetCore.Mvc;
using System.Threading.Tasks;

namespace Booking.Web.Controllers
{
    public class FlightController : Controller
    {
        private readonly IAmadeusService _amadeusService;

        public FlightController(IAmadeusService amadeusService)
        {
            _amadeusService = amadeusService;
        }

        public IActionResult Index(string origin = "SGN", string destination = "HAN", string departureDate = "", string returnDate = "", string adults = "1")
        {
            if (string.IsNullOrEmpty(departureDate))
            {
                departureDate = System.DateTime.Today.AddDays(7).ToString("yyyy-MM-dd");
            }
            
            ViewData["Origin"] = origin;
            ViewData["Destination"] = destination;
            ViewData["DepartureDate"] = departureDate;
            ViewData["ReturnDate"] = returnDate;
            ViewData["Adults"] = adults;
            
            return View();
        }

        [HttpPost("api/flight/search")]
        public async Task<IActionResult> SearchApi([FromBody] SearchFlightRequest request)
        {
            if (request == null || string.IsNullOrEmpty(request.OriginLocationCode) || string.IsNullOrEmpty(request.DestinationLocationCode))
            {
                return BadRequest("Invalid request parameters");
            }

            var flights = await _amadeusService.SearchFlightsAsync(request);
            
            var result = new PaginatedResult<FlightDto>
            {
                TotalItems = flights.Count,
                Page = 1,
                PageSize = request.Max,
                TotalPages = 1,
                Items = flights
            };

            return Ok(result);
        }
    }
}
