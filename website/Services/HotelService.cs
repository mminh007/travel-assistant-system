using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Booking.Web.Data;
using Booking.Web.Models.Domain;
using Booking.Web.Models.DTOs;
using Booking.Web.Services.Interfaces;
using Microsoft.EntityFrameworkCore;

namespace Booking.Web.Services
{
    public class HotelService : IHotelService
    {
        private readonly AppDbContext _context;
        public HotelService(AppDbContext context)
        {
            _context = context;
        }

        public async Task<Hotel?> GetHotelDetailAsync(Guid id)
        {
            return await _context.Hotels
                .Include(h => h.RoomTypes)
                .FirstOrDefaultAsync(h => h.Id == id);
        }

        public async Task<PaginatedResult<HotelDto>> SearchHotelsAsync(SearchHotelRequest request)
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

            // 2. Filter by Occupancy
            int totalGuests = request.Adults + request.Children;
            if (request.Rooms > 0)
            {
                int minOccupancyPerRoom = (int)Math.Ceiling((double)totalGuests / request.Rooms);
                query = query.Where(h => h.RoomTypes.Any(rt => rt.MaxOccupancy >= minOccupancyPerRoom));
            }

            // 3. Filter by Property Types
            if (request.PropertyTypes != null && request.PropertyTypes.Any())
            {
                query = query.Where(h => h.RoomTypes.Any(rt => request.PropertyTypes.Contains(rt.Type)));
            }

            if (request.MinRating.HasValue)
            {
                query = query.Where(h => h.StarRating >= request.MinRating.Value);
            }

            if (request.MaxRating.HasValue)
            {
                query = query.Where(h => h.StarRating <= request.MaxRating.Value);
            }

            // Execute DB query to get filtered hotels
            var hotels = await query.ToListAsync();

            // 4. Transform and Filter by Price
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
                    TopAmenities = amenities.Take(4).ToList()
                });
            }

            // 5. Sort & Pagination
            var totalItems = resultList.Count;

            IEnumerable<HotelDto> sorted = request.SortBy switch
            {
                "price_asc"  => resultList.OrderBy(h => h.MinPricePerNight),
                "price_desc" => resultList.OrderByDescending(h => h.MinPricePerNight),
                "star_desc"  => resultList.OrderByDescending(h => h.StarRating),
                "star_asc"   => resultList.OrderBy(h => h.StarRating),
                "name_asc"   => resultList.OrderBy(h => h.Name),
                _            => resultList.OrderBy(h => h.MinPricePerNight)
            };

            var pagedItems = sorted
                .Skip((request.Page - 1) * request.PageSize)
                .Take(request.PageSize)
                .ToList();

            return new PaginatedResult<HotelDto>
            {
                Items = pagedItems,
                TotalItems = totalItems,
                CurrentPage = request.Page,
                PageSize = request.PageSize,
                TotalPages = (int)Math.Ceiling(totalItems / (double)request.PageSize)
            };
        }
    }
}
