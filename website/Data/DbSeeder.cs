using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Booking.Web.Models.Domain;

namespace Booking.Web.Data
{
    public static class DbSeeder
    {
        private class HotelSeedData 
        {
            public string Name { get; set; } = string.Empty;
            public string Address { get; set; } = string.Empty;
            public string City { get; set; } = string.Empty;
            public string PhoneNumber { get; set; } = string.Empty;
        }

        public static void SeedData(IApplicationBuilder app)
        {
            using (var scope = app.ApplicationServices.CreateScope())
            {
                var context = scope.ServiceProvider.GetRequiredService<AppDbContext>();

                if (!context.Hotels.Any())
                {
                    var filePath = Path.Combine(Directory.GetCurrentDirectory(), "Data", "hotels_seed.json");
                    if (!File.Exists(filePath)) return;

                    var jsonString = File.ReadAllText(filePath);
                    var hotelSeeds = JsonSerializer.Deserialize<List<HotelSeedData>>(jsonString);

                    if (hotelSeeds == null || !hotelSeeds.Any()) return;

                    var random = new Random();
                    var hotels = new List<Hotel>();

                    foreach (var h in hotelSeeds)
                    {
                        var hotel = new Hotel
                        {
                            Id = Guid.NewGuid(),
                            Name = h.Name,
                            Address = h.Address,
                            City = h.City,
                            Country = "Vietnam",
                            PhoneNumber = h.PhoneNumber,
                            StarRating = random.Next(3, 6),
                            Description = "Mô tả mẫu cho khách sạn này được tạo tự động.",
                            ThumbnailUrl = "https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                            Latitude = random.NextDouble() * (16.5 - 12.0) + 12.0, // random VN lat
                            Longitude = random.NextDouble() * (109.5 - 107.0) + 107.0,
                        };
                        hotels.Add(hotel);
                    }

                    context.Hotels.AddRange(hotels);
                    context.SaveChanges();

                    var roomTypes = new List<RoomType>();

                    foreach (var hotel in hotels)
                    {
                        string nameLower = hotel.Name.ToLower();

                        // 1. Check if Resort
                        if (nameLower.Contains("resort") || nameLower.Contains("lodge") || nameLower.Contains("spa"))
                        {
                            // Resort Room Types from PDF
                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Garden View Villa",
                                Type = "Resort",
                                Description = "Biệt thự hướng vườn rộng rãi với dịch vụ cao cấp.",
                                PricePerNight = random.Next(180, 250) * 10000,
                                MaxOccupancy = 2,
                                TotalRooms = random.Next(5, 15),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1583037189850-1921ae7c6c22?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Ăn sáng buffet", "Hồ bơi riêng", "Xe điện di chuyển nội khu", "Dịch vụ Spa 30 phút" })
                            });

                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Beachfront Pool Villa",
                                Type = "Resort",
                                Description = "Biệt thự sát biển có hồ bơi riêng biệt và quản gia phục vụ.",
                                PricePerNight = random.Next(350, 600) * 10000,
                                MaxOccupancy = 4,
                                TotalRooms = random.Next(2, 6),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1576013551627-0cc20b96c2a7?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Quản gia riêng", "Hồ bơi vô cực riêng", "Tiệc BBQ bãi biển", "Đưa đón sân bay hạng sang" })
                            });

                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Family Pavilion",
                                Type = "Resort",
                                Description = "Không gian rộng lớn hoàn hảo cho kỳ nghỉ của cả gia đình.",
                                PricePerNight = random.Next(280, 420) * 10000,
                                MaxOccupancy = 5,
                                TotalRooms = random.Next(3, 8),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1591088398332-8a7791972843?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Ăn sáng gia đình", "Khu vui chơi trẻ em", "Trực tiếp ra biển", "Trà chiều" })
                            });
                        }
                        // 2. Check if Apartment / Residence
                        else if (nameLower.Contains("apartment") || nameLower.Contains("residence"))
                        {
                            // Apartment Room Types from PDF
                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Studio Apartment",
                                Type = "Apartment",
                                Description = "Căn hộ studio đầy đủ tiện nghi, phù hợp cho kỳ lưu trú dài ngày.",
                                PricePerNight = random.Next(90, 140) * 10000,
                                MaxOccupancy = 2,
                                TotalRooms = random.Next(10, 30),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Bếp đầy đủ tiện nghi", "Máy giặt & sấy", "Dịch vụ dọn phòng hàng ngày" })
                            });

                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "2-Bedroom Residence",
                                Type = "Apartment",
                                Description = "Căn hộ 2 phòng ngủ sang trọng với ban công view toàn cảnh.",
                                PricePerNight = random.Next(180, 260) * 10000,
                                MaxOccupancy = 4,
                                TotalRooms = random.Next(5, 15),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Phòng khách riêng", "Bếp hiện đại", "Ban công ngắm cảnh", "Hồ bơi tầng thượng" })
                            });

                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Penthouse Suite",
                                Type = "Apartment",
                                Description = "Căn hộ thông tầng cao cấp nhất tòa nhà với phòng xông hơi riêng.",
                                PricePerNight = random.Next(400, 700) * 10000,
                                MaxOccupancy = 6,
                                TotalRooms = random.Next(1, 4),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1600566752355-35792bedcfea?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Thang máy riêng", "Sân thượng panorama", "Phòng xông hơi riêng", "Dịch vụ đi chợ hộ" })
                            });
                        }
                        // 3. Fallback to Hotel
                        else
                        {
                            // Hotel Room Types from PDF
                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Standard Room",
                                Type = "Hotel",
                                Description = "Phòng tiêu chuẩn ấm cúng với đầy đủ trang thiết bị tiện nghi.",
                                PricePerNight = random.Next(60, 90) * 10000,
                                MaxOccupancy = 2,
                                TotalRooms = random.Next(20, 50),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1611892440504-42a792e24d32?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Ăn sáng miễn phí", "Wifi tốc độ cao", "Nước uống chào mừng" })
                            });

                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Deluxe Ocean View",
                                Type = "Hotel",
                                Description = "Phòng cao cấp hướng biển đem đến không gian lãng mạn.",
                                PricePerNight = random.Next(110, 170) * 10000,
                                MaxOccupancy = 2,
                                TotalRooms = random.Next(10, 20),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1590490360182-c33d57733427?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Ăn sáng buffet", "Wifi", "Hồ bơi vô cực", "Trà & Cà phê" })
                            });

                            roomTypes.Add(new RoomType
                            {
                                Id = Guid.NewGuid(),
                                HotelId = hotel.Id,
                                Name = "Executive Suite",
                                Type = "Hotel",
                                Description = "Phòng VIP cao cấp với phòng khách riêng biệt và đón tiễn sân bay.",
                                PricePerNight = random.Next(200, 320) * 10000,
                                MaxOccupancy = 3,
                                TotalRooms = random.Next(2, 6),
                                ThumbnailUrl = "https://images.unsplash.com/photo-1578683010236-d716f9a3f461?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80",
                                Amenities = JsonSerializer.Serialize(new List<string> { "Ăn sáng tại phòng", "Đưa đón sân bay", "Minibar miễn phí", "Giặt ủi" })
                            });
                        }
                    }

                    context.RoomTypes.AddRange(roomTypes);
                    context.SaveChanges();
                }
            }
        }
    }
}
