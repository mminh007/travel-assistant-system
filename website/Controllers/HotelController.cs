using Microsoft.AspNetCore.Mvc;
using Booking.Web.Data;
using Microsoft.EntityFrameworkCore;
using Booking.Web.Models.DTOs;
using System.Linq;
using System.Text.Json;
using Booking.Web.Models.Domain;

namespace Booking.Web.Controllers
{
    public class HotelController : Controller
    {
        private readonly AppDbContext _context;

        public HotelController(AppDbContext context)
        {
            _context = context;
        }

        // Action for rendering the View (Search Page)
        public IActionResult Search(string destination, string dates, string guests)
        {
            ViewData["Destination"] = destination;
            ViewData["Dates"] = dates;
            ViewData["Guests"] = guests;
            
            return View(new List<Hotel>());
        }

        [HttpPost("api/hotel/search")]
        public async Task<IActionResult> SearchApi([FromBody] SearchHotelRequest request)
        {
            var query = _context.Hotels
                .Include(h => h.RoomTypes)
                .AsQueryable();

            // 1. Filter by Destination
            if (!string.IsNullOrWhiteSpace(request.Destination))
            {
                var dest = request.Destination.Trim().ToLower();
                query = query.Where(h => h.City.ToLower().Contains(dest) || h.Name.ToLower().Contains(dest));
            }

            // 2. Filter by Occupancy (Simple check: total guests can fit in the requested rooms)
            // A more complex check would find exact combinations, but this is a good approximation
            int totalGuests = request.Adults + request.Children;
            if (request.Rooms > 0)
            {
                // Each room needs to hold at least (totalGuests / request.Rooms) roughly.
                // We'll filter out hotels that do NOT have any room type that can accommodate the max needed per room.
                int minOccupancyPerRoom = (int)Math.Ceiling((double)totalGuests / request.Rooms);
                
                query = query.Where(h => h.RoomTypes.Any(rt => rt.MaxOccupancy >= minOccupancyPerRoom));
            }

            // 3. Filter by Property Types (Hotel, Resort, Apartment)
            if (request.PropertyTypes != null && request.PropertyTypes.Any())
            {
                query = query.Where(h => h.RoomTypes.Any(rt => request.PropertyTypes.Contains(rt.Type)));
            }

            // Execute DB query to get filtered hotels
            var hotels = await query.ToListAsync();

            // 4. Transform and Filter by Price (in-memory for simplicity, or can be done in DB)
            var resultList = new List<HotelDto>();
            foreach (var h in hotels)
            {
                var matchingRooms = h.RoomTypes.AsEnumerable();

                if (request.PropertyTypes != null && request.PropertyTypes.Any())
                {
                    matchingRooms = matchingRooms.Where(rt => request.PropertyTypes.Contains(rt.Type));
                }

                if (!matchingRooms.Any()) continue;

                var minPrice = matchingRooms.Min(rt => rt.PricePerNight);

                if (request.MinPrice.HasValue && minPrice < request.MinPrice.Value) continue;
                if (request.MaxPrice.HasValue && minPrice > request.MaxPrice.Value) continue;

                // Extract top amenities from room types
                var amenities = new HashSet<string>();
                foreach (var rt in matchingRooms)
                {
                    try
                    {
                        var list = JsonSerializer.Deserialize<List<string>>(rt.Amenities);
                        if (list != null)
                        {
                            foreach (var a in list) amenities.Add(a);
                        }
                    }
                    catch { /* ignore invalid json */ }
                }

                resultList.Add(new HotelDto
                {
                    Id = h.Id,
                    Name = h.Name,
                    Address = h.Address,
                    City = h.City,
                    StarRating = h.StarRating,
                    ThumbnailUrl = h.ThumbnailUrl,
                    MinPricePerNight = minPrice,
                    PropertyTypes = matchingRooms.Select(rt => rt.Type).Distinct().ToList(),
                    TopAmenities = amenities.Take(4).ToList() // take top 4 unique amenities
                });
            }

            // 5. Pagination
            var totalItems = resultList.Count;
            var pagedItems = resultList
                .OrderBy(h => h.MinPricePerNight) // default sort
                .Skip((request.Page - 1) * request.PageSize)
                .Take(request.PageSize)
                .ToList();

            var result = new PaginatedResult<HotelDto>
            {
                Items = pagedItems,
                TotalItems = totalItems,
                CurrentPage = request.Page,
                PageSize = request.PageSize,
                TotalPages = (int)Math.Ceiling(totalItems / (double)request.PageSize)
            };

            return Ok(result);
        }
    }
}
