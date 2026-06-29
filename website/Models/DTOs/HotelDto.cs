using System;
using System.Collections.Generic;

namespace Booking.Web.Models.DTOs
{
    public class HotelDto
    {
        public Guid Id { get; set; }
        public string Name { get; set; } = string.Empty;
        public string Address { get; set; } = string.Empty;
        public string City { get; set; } = string.Empty;
        public int StarRating { get; set; }
        public string ThumbnailUrl { get; set; } = string.Empty;
        public decimal MinPricePerNight { get; set; }
        public List<string> PropertyTypes { get; set; } = new List<string>();
        public List<string> TopAmenities { get; set; } = new List<string>();
    }
}
