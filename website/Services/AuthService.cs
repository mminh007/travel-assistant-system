using System;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.IdentityModel.Tokens;
using Microsoft.EntityFrameworkCore;
using Booking.Web.Data;
using Booking.Web.Models.Domain;
using Booking.Web.Models.ViewModels;

namespace Booking.Web.Services
{
    public class AuthService : IAuthService
    {
        private readonly AppDbContext _context;
        private readonly IConfiguration _config;

        public AuthService(AppDbContext context, IConfiguration config)
        {
            _context = context;
            _config = config;
        }

        public async Task<AuthResponseViewModel> LoginAsync(LoginViewModel model, string deviceInfo)
        {
            var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == model.Email);
            if (user == null || !VerifyPasswordHash(model.Password, user.PasswordHash))
            {
                return new AuthResponseViewModel { Success = false, Message = "Invalid email or password." };
            }

            var jwtToken = GenerateJwtToken(user);
            var refreshToken = GenerateRefreshToken(user.Id, deviceInfo);

            await _context.RefreshTokens.AddAsync(refreshToken);
            await _context.SaveChangesAsync();

            return new AuthResponseViewModel
            {
                Success = true,
                Message = "Login successful",
                JwtToken = jwtToken,
                RefreshToken = refreshToken.Token
            };
        }

        public async Task<AuthResponseViewModel> RegisterAsync(RegisterViewModel model, string deviceInfo)
        {
            if (await _context.Users.AnyAsync(u => u.Email == model.Email))
            {
                return new AuthResponseViewModel { Success = false, Message = "Email already exists." };
            }

            var user = new User
            {
                Email = model.Email,
                FullName = model.FullName,
                PasswordHash = HashPassword(model.Password)
            };

            await _context.Users.AddAsync(user);
            await _context.SaveChangesAsync();

            var jwtToken = GenerateJwtToken(user);
            var refreshToken = GenerateRefreshToken(user.Id, deviceInfo);

            await _context.RefreshTokens.AddAsync(refreshToken);
            await _context.SaveChangesAsync();

            return new AuthResponseViewModel
            {
                Success = true,
                Message = "Registration successful",
                JwtToken = jwtToken,
                RefreshToken = refreshToken.Token
            };
        }

        public async Task<AuthResponseViewModel> RefreshTokenAsync(string tokenStr, string deviceInfo)
        {
            var refreshToken = await _context.RefreshTokens
                .Include(r => r.User)
                .FirstOrDefaultAsync(r => r.Token == tokenStr);

            if (refreshToken == null || refreshToken.IsRevoked || refreshToken.ExpiresAt <= DateTime.UtcNow)
            {
                return new AuthResponseViewModel { Success = false, Message = "Invalid or expired refresh token." };
            }

            // Revoke old token
            refreshToken.IsRevoked = true;

            // Generate new pairs
            var newJwtToken = GenerateJwtToken(refreshToken.User);
            var newRefreshToken = GenerateRefreshToken(refreshToken.UserId, deviceInfo);

            await _context.RefreshTokens.AddAsync(newRefreshToken);
            await _context.SaveChangesAsync();

            return new AuthResponseViewModel
            {
                Success = true,
                Message = "Token refreshed",
                JwtToken = newJwtToken,
                RefreshToken = newRefreshToken.Token
            };
        }

        public async Task<bool> LogoutAsync(string tokenStr)
        {
            var refreshToken = await _context.RefreshTokens.FirstOrDefaultAsync(r => r.Token == tokenStr);
            if (refreshToken != null)
            {
                refreshToken.IsRevoked = true;
                await _context.SaveChangesAsync();
                return true;
            }
            return false;
        }

        public async Task<User?> GetUserByIdAsync(Guid userId)
        {
            return await _context.Users.FindAsync(userId);
        }

        private string GenerateJwtToken(User user)
        {
            var jwtSettings = _config.GetSection("JwtSettings");
            var key = Encoding.ASCII.GetBytes(jwtSettings["SecretKey"]);
            
            // Note: Generate a random session Id for the agent
            var sessionId = Guid.NewGuid().ToString();

            var tokenDescriptor = new SecurityTokenDescriptor
            {
                Subject = new ClaimsIdentity(new[]
                {
                    new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()),
                    new Claim(ClaimTypes.Email, user.Email),
                    new Claim(ClaimTypes.Role, user.Role),
                    new Claim("sessionId", sessionId),
                    new Claim("FullName", user.FullName)
                }),
                Expires = DateTime.UtcNow.AddMinutes(double.Parse(jwtSettings["TokenExpirationMinutes"])),
                Issuer = jwtSettings["Issuer"],
                Audience = jwtSettings["Audience"],
                SigningCredentials = new SigningCredentials(new SymmetricSecurityKey(key), SecurityAlgorithms.HmacSha256Signature)
            };

            var tokenHandler = new JwtSecurityTokenHandler();
            var token = tokenHandler.CreateToken(tokenDescriptor);
            return tokenHandler.WriteToken(token);
        }

        private RefreshToken GenerateRefreshToken(Guid userId, string deviceInfo)
        {
            var randomBytes = new byte[64];
            using (var rng = RandomNumberGenerator.Create())
            {
                rng.GetBytes(randomBytes);
            }

            var days = double.Parse(_config.GetSection("JwtSettings")["RefreshTokenExpirationDays"]);

            return new RefreshToken
            {
                UserId = userId,
                Token = Convert.ToBase64String(randomBytes),
                ExpiresAt = DateTime.UtcNow.AddDays(days),
                DeviceInfo = deviceInfo
            };
        }

        private string HashPassword(string password)
        {
            // Simple hash for demo purposes. In production use BCrypt or ASP.NET Core Identity PasswordHasher.
            using (var sha256 = SHA256.Create())
            {
                var hashedBytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(password));
                return Convert.ToBase64String(hashedBytes);
            }
        }

        private bool VerifyPasswordHash(string password, string hash)
        {
            return HashPassword(password) == hash;
        }
    }
}
