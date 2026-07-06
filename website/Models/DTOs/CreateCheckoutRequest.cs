namespace Booking.Web.Models.DTOs
{
    public class CreateCheckoutRequest
    {
        public Guid RoomTypeId { get; set; }
        public DateTime CheckIn { get; set; }
        public DateTime CheckOut { get; set; }
        public int Guests { get; set; }
        public string? GuestName { get; set; }
        public string? GuestEmail { get; set; }
        public string? PhoneNumber { get; set; }
        public string? SpecialRequests { get; set; }
    }
}
