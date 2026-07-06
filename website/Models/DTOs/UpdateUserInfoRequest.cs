namespace Booking.Web.Models.DTOs
{
    public class UpdateUserInfoRequest
    {
        public string? FullName { get; set; }
        public string? PhoneNumber { get; set; }
        public string? Address { get; set; }
        public string? Nationality { get; set; }
    }
}
