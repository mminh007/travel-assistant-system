using System.Collections.Generic;

namespace Booking.Web.Models.DTOs
{
    public class FlightDto
    {
        public string Id { get; set; } = string.Empty;
        public string AirlineName { get; set; } = string.Empty;
        public string AirlineLogoUrl { get; set; } = string.Empty;
        public string DepartureTime { get; set; } = string.Empty;
        public string ArrivalTime { get; set; } = string.Empty;
        public string Duration { get; set; } = string.Empty;
        public string DepartureCode { get; set; } = string.Empty;
        public string ArrivalCode { get; set; } = string.Empty;
        public string TotalPrice { get; set; } = string.Empty;
        public string Currency { get; set; } = string.Empty;
        public int Stops { get; set; }
        
        // If it's a round trip, we might have a return flight block
        public FlightRouteDto? ReturnFlight { get; set; }
    }

    public class FlightRouteDto
    {
        public string DepartureTime { get; set; } = string.Empty;
        public string ArrivalTime { get; set; } = string.Empty;
        public string Duration { get; set; } = string.Empty;
        public string DepartureCode { get; set; } = string.Empty;
        public string ArrivalCode { get; set; } = string.Empty;
        public int Stops { get; set; }
    }
}
