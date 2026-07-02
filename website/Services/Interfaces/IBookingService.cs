using System;
using System.Threading.Tasks;
using Booking.Web.Models.Domain;

namespace Booking.Web.Services.Interfaces
{
    public interface IBookingService
    {
        Task<RoomType?> GetRoomTypeWithHotelAsync(Guid roomTypeId);
        Task<BookingRecord> CreatePendingBookingAsync(Guid userId, Guid roomTypeId, Guid hotelId, DateTime checkIn, DateTime checkOut, int nights, int guests, decimal totalPrice, string? guestName = null, string? guestEmail = null, string? phoneNumber = null, string? specialRequests = null);
        Task<bool> ConfirmBookingAndRecordPaymentAsync(Guid bookingId, string currency, string transactionId, decimal amount);
    }
}
