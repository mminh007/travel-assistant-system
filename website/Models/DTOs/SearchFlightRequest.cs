using System;

namespace Booking.Web.Models.DTOs
{
    public class SearchFlightRequest
    {
        public string OriginLocationCode { get; set; } = string.Empty;
        public string DestinationLocationCode { get; set; } = string.Empty;
        public string DepartureDate { get; set; } = string.Empty;
        public string? ReturnDate { get; set; }
        public int Adults { get; set; } = 1;
        public int Max { get; set; } = 20; // Number of results
        public string SortBy { get; set; } = "best";
    }
}
