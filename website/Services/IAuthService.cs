using System.Threading.Tasks;
using Booking.Web.Models.ViewModels;
using Booking.Web.Models.Domain;

namespace Booking.Web.Services
{
    public interface IAuthService
    {
        Task<AuthResponseViewModel> LoginAsync(LoginViewModel model, string deviceInfo);
        Task<AuthResponseViewModel> RegisterAsync(RegisterViewModel model, string deviceInfo);
        Task<AuthResponseViewModel> RefreshTokenAsync(string refreshToken, string deviceInfo);
        Task<bool> LogoutAsync(string refreshToken);
        Task<User?> GetUserByIdAsync(System.Guid userId);
    }
}
