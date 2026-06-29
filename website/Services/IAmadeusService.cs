using Booking.Web.Models.DTOs;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Booking.Web.Services
{
    public interface IAmadeusService
    {
        Task<List<FlightDto>> SearchFlightsAsync(SearchFlightRequest request);
    }
}
