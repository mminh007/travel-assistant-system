using System.Collections.Generic;

namespace Booking.Web.Models.DTOs
{
    public class PaginatedResult<T>
    {
        public List<T> Items { get; set; } = new List<T>();
        public int TotalItems { get; set; }
        public int CurrentPage { get; set; }
        public int TotalPages { get; set; }
        public int PageSize { get; set; }
        public int Page { get; set; }  
    }
}
