using System;
using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Booking.Web.Models.Domain
{
    public class Payment
    {
        [Key]
        public Guid Id { get; set; } = Guid.NewGuid();

        public Guid? BookingId { get; set; }
        [ForeignKey("BookingId")]
        public BookingRecord? BookingRecord { get; set; }

        [Required]
        public Guid UserId { get; set; }
        [ForeignKey("UserId")]
        public User User { get; set; } = null!;

        [Column(TypeName = "decimal(18,2)")]
        public decimal Amount { get; set; }

        [MaxLength(10)]
        public string Currency { get; set; } = "VND";

        [MaxLength(50)]
        public string PaymentMethod { get; set; } = "Stripe";

        [MaxLength(256)]
        public string TransactionId { get; set; } = string.Empty;

        [MaxLength(50)]
        public string Status { get; set; } = "Pending"; // Pending, Success, Failed

        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    }
}
