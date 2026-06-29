using System;
using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Booking.Web.Models.Domain
{
    public class RoomType
    {
        [Key]
        public Guid Id { get; set; } = Guid.NewGuid();

        [Required]
        public Guid HotelId { get; set; }
        [ForeignKey("HotelId")]
        public Hotel Hotel { get; set; } = null!;

        [Required]
        [MaxLength(256)]
        public string Name { get; set; } = string.Empty;

        [MaxLength(50)]
        public string Type { get; set; } = "Hotel"; // Resort, Hotel, Apartment

        public string Description { get; set; } = string.Empty;

        [Column(TypeName = "decimal(18,2)")]
        public decimal PricePerNight { get; set; }

        public int MaxOccupancy { get; set; }

        public string ThumbnailUrl { get; set; } = string.Empty;

        public bool IsAvailable { get; set; } = true;

        public int TotalRooms { get; set; }

        public string Amenities { get; set; } = "[]"; // Store JSON array of amenities
    }
}
