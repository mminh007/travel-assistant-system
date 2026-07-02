using Microsoft.AspNetCore.Mvc;
using Booking.Web.Models.DTOs;
using System.Threading.Tasks;
using Booking.Web.Services.Interfaces;

namespace Booking.Web.Controllers
{
    public class HotelController : Controller
    {
        private readonly IHotelService _hotelService;

        public HotelController(IHotelService hotelService)
        {
            _hotelService = hotelService;
        }

        // Action for rendering the View (Search Page)
        public IActionResult Search(string destination, string dates, string guests)
        {
            ViewData["Destination"] = destination;
            ViewData["Dates"] = dates;
            ViewData["Guests"] = guests;
            
            return View(new List<Booking.Web.Models.Domain.Hotel>());
        }

        // Action for rendering the Hotel Detail Page
        [HttpGet("Hotel/Detail/{id}")]
        public async Task<IActionResult> Detail(Guid id)
        {
            var hotel = await _hotelService.GetHotelDetailAsync(id);

            if (hotel == null)
            {
                return NotFound();
            }

            return View(hotel);
        }

        [HttpPost("api/hotel/search")]
        public async Task<IActionResult> SearchApi([FromBody] SearchHotelRequest request)
        {
            var result = await _hotelService.SearchHotelsAsync(request);
            return Ok(result);
        }
    }
}

