using System;
using System.Threading.Tasks;
using Booking.Web.Data;
using Booking.Web.Models.Domain;
using Booking.Web.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

namespace Booking.Web.Services
{
    public class BookingService : IBookingService
    {
        private readonly AppDbContext _context;

        public BookingService(AppDbContext context)
        {
            _context = context;
        }

        public async Task<RoomType?> GetRoomTypeWithHotelAsync(Guid roomTypeId)
        {
            return await _context.RoomTypes
                .Include(rt => rt.Hotel)
                .FirstOrDefaultAsync(rt => rt.Id == roomTypeId);
        }

        public async Task<BookingRecord> CreatePendingBookingAsync(Guid userId, Guid roomTypeId, Guid hotelId, DateTime checkIn, DateTime checkOut, int nights, int guests, decimal totalPrice, string? guestName = null, string? guestEmail = null, string? phoneNumber = null, string? specialRequests = null)
        {
            var booking = new BookingRecord
            {
                Id = Guid.NewGuid(),
                UserId = userId,
                RoomTypeId = roomTypeId,
                HotelId = hotelId,
                CheckInDate = checkIn,
                CheckOutDate = checkOut,
                TotalNights = nights,
                GuestCount = guests,
                TotalPrice = totalPrice,
                Status = "Pending",
                GuestName = guestName,
                GuestEmail = guestEmail,
                PhoneNumber = phoneNumber,
                SpecialRequests = specialRequests
            };

            _context.Bookings.Add(booking);
            await _context.SaveChangesAsync();

            return booking;
        }

        public async Task<bool> ConfirmBookingAndRecordPaymentAsync(Guid bookingId, string currency, string transactionId, decimal amount)
        {
            var booking = await _context.Bookings.FindAsync(bookingId);
            if (booking == null) return false;

            if (booking.Status == "Success")
            {
                // Already processed (idempotent return)
                return true;
            }

            booking.Status = "Success";
            _context.Bookings.Update(booking);

            var payment = new Payment
            {
                Id = Guid.NewGuid(),
                BookingId = booking.Id,
                UserId = booking.UserId,
                Amount = amount,
                Currency = currency,
                CreatedAt = DateTime.UtcNow,
                TransactionId = transactionId,
                Status = "Success"
            };

            _context.Payments.Add(payment);
            await _context.SaveChangesAsync();

            return true;
        }

        public async Task<System.Collections.Generic.IEnumerable<BookingRecord>> GetBookingsByUserIdAsync(Guid userId)
        {
            return await _context.Bookings
                .Include(b => b.RoomType)
                .ThenInclude(rt => rt.Hotel)
                .Where(b => b.UserId == userId)
                .OrderByDescending(b => b.CreatedAt)
                .ToListAsync();
        }

        public async Task<bool> CancelBookingAsync(Guid bookingId, Guid userId)
        {
            var booking = await _context.Bookings.FirstOrDefaultAsync(b => b.Id == bookingId && b.UserId == userId);
            
            if (booking == null) return false;

            if (booking.Status == "Cancelled") return true; // Already cancelled

            var hoursSinceCreation = (DateTime.UtcNow - booking.CreatedAt).TotalHours;
            if (hoursSinceCreation > 24)
            {
                return false; // Cannot cancel after 24 hours
            }

            booking.Status = "Cancelled";
            booking.UpdatedAt = DateTime.UtcNow;
            
            _context.Bookings.Update(booking);
            await _context.SaveChangesAsync();

            return true;
        }
    }
}
