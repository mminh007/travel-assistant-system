using System;
using System.ComponentModel.DataAnnotations;

namespace Booking.Web.Models.Domain
{
    public class Hotel
    {
        [Key]
        public Guid Id { get; set; } = Guid.NewGuid();

        [Required]
        [MaxLength(256)]
        public string Name { get; set; } = string.Empty;

        public string Description { get; set; } = string.Empty;

        [MaxLength(500)]
        public string Address { get; set; } = string.Empty;

        [MaxLength(100)]
        public string City { get; set; } = string.Empty;

        [MaxLength(100)]
        public string Country { get; set; } = string.Empty;

        [MaxLength(50)]
        public string PhoneNumber { get; set; } = string.Empty;

        [Range(1, 5)]
        public int StarRating { get; set; }

        public string ThumbnailUrl { get; set; } = string.Empty;

        public double Latitude { get; set; }
        public double Longitude { get; set; }

        public string Amenities { get; set; } = "[]"; // Store JSON array

        public bool IsActive { get; set; } = true;

        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

        public virtual ICollection<RoomType> RoomTypes { get; set; } = new List<RoomType>();
    }
}
