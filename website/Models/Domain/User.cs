using System;
using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;

namespace Booking.Web.Models.Domain
{
    public class User
    {
        [Key]
        public Guid Id { get; set; } = Guid.NewGuid();

        [Required]
        [EmailAddress]
        [MaxLength(256)]
        public string Email { get; set; } = string.Empty;

        [Required]
        public string PasswordHash { get; set; } = string.Empty;

        [MaxLength(256)]
        public string FullName { get; set; } = string.Empty;

        [MaxLength(50)]
        public string PhoneNumber { get; set; } = string.Empty;

        public string AvatarUrl { get; set; } = string.Empty;

        [MaxLength(20)]
        public string Role { get; set; } = "User";

        public bool IsEmailVerified { get; set; } = false;

        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
        public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
    }
}
