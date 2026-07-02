using System;
using System.Collections.Generic;

namespace Booking.Web.Models.DTOs
{
    public class SearchHotelRequest
    {
        public string Destination { get; set; } = string.Empty;
        public DateTime? CheckIn { get; set; }
        public DateTime? CheckOut { get; set; }
        public int Adults { get; set; } = 2;
        public int Children { get; set; } = 0;
        public int Rooms { get; set; } = 1;
        public decimal? MinPrice { get; set; }
        public decimal? MaxPrice { get; set; }
        public List<string>? PropertyTypes { get; set; }
        public int? MinRating { get; set; }
        public int? MaxRating { get; set; }
        public int Page { get; set; } = 1;
        public int PageSize { get; set; } = 10;
        public string SortBy { get; set; } = "price_asc";
    }
}
