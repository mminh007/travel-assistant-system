using System;
using System.Threading.Tasks;
using Booking.Web.Models.Domain;
using Booking.Web.Models.DTOs;

namespace Booking.Web.Services.Interfaces
{
    public interface IHotelService
    {
        Task<Hotel?> GetHotelDetailAsync(Guid id);
        Task<PaginatedResult<HotelDto>> SearchHotelsAsync(SearchHotelRequest request);
    }
}
