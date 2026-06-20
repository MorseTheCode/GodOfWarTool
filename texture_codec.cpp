#include <cstddef>
#include <cstdint>
#include <cstring>

static std::uint64_t tiled_offset(
    std::uint32_t block_x,
    std::uint32_t block_y,
    std::uint32_t block_columns,
    std::uint32_t bytes_per_block)
{
    std::uint32_t page_width;
    std::uint32_t page_height = 16;
    std::uint32_t element;
    if (bytes_per_block == 8) {
        page_width = 32;
        const std::uint32_t x = block_x & 31;
        const std::uint32_t y = block_y & 15;
        element =
            (((x >> 0) & 1) << 0) |
            (((y >> 0) & 1) << 1) |
            (((y >> 1) & 1) << 2) |
            (((x >> 1) & 1) << 3) |
            (((x >> 2) & 1) << 4) |
            (((y >> 2) & 1) << 5) |
            (((x >> 3) & 1) << 6) |
            (((y >> 3) & 1) << 7) |
            (((x >> 4) & 1) << 8);
    } else {
        page_width = 16;
        const std::uint32_t x = block_x & 15;
        const std::uint32_t y = block_y & 15;
        element =
            (((y >> 0) & 1) << 0) |
            (((y >> 1) & 1) << 1) |
            (((x >> 0) & 1) << 2) |
            (((x >> 1) & 1) << 3) |
            (((y >> 2) & 1) << 4) |
            (((x >> 2) & 1) << 5) |
            (((y >> 3) & 1) << 6) |
            (((x >> 3) & 1) << 7);
    }
    const std::uint64_t page_columns =
        (block_columns + page_width - 1) / page_width;
    const std::uint64_t page_index =
        (block_y / page_height) * page_columns + block_x / page_width;
    return page_index * 4096 +
        static_cast<std::uint64_t>(element) * bytes_per_block;
}

extern "C" __declspec(dllexport) int ps5_unswizzle(
    const std::uint8_t* tiled,
    std::size_t tiled_size,
    std::uint8_t* linear,
    std::size_t linear_size,
    std::size_t source_base,
    std::uint32_t columns,
    std::uint32_t rows,
    std::uint32_t bytes_per_block)
{
    if (!tiled || !linear || !bytes_per_block ||
        linear_size != static_cast<std::size_t>(columns) * rows * bytes_per_block) {
        return 0;
    }
    std::memset(linear, 0, linear_size);
    for (std::uint32_t y = 0; y < rows; ++y) {
        for (std::uint32_t x = 0; x < columns; ++x) {
            const std::size_t source = source_base +
                static_cast<std::size_t>(tiled_offset(x, y, columns, bytes_per_block));
            const std::size_t destination =
                (static_cast<std::size_t>(y) * columns + x) * bytes_per_block;
            if (source + bytes_per_block <= tiled_size) {
                std::memcpy(linear + destination, tiled + source, bytes_per_block);
            }
        }
    }
    return 1;
}

extern "C" __declspec(dllexport) int ps5_swizzle(
    const std::uint8_t* linear,
    std::size_t linear_size,
    std::uint8_t* tiled,
    std::size_t tiled_size,
    std::size_t destination_base,
    std::uint32_t columns,
    std::uint32_t rows,
    std::uint32_t bytes_per_block)
{
    if (!linear || !tiled || !bytes_per_block ||
        linear_size != static_cast<std::size_t>(columns) * rows * bytes_per_block) {
        return 0;
    }
    for (std::uint32_t y = 0; y < rows; ++y) {
        for (std::uint32_t x = 0; x < columns; ++x) {
            const std::size_t source =
                (static_cast<std::size_t>(y) * columns + x) * bytes_per_block;
            const std::size_t destination = destination_base +
                static_cast<std::size_t>(tiled_offset(x, y, columns, bytes_per_block));
            if (destination + bytes_per_block > tiled_size) {
                return 0;
            }
            std::memcpy(tiled + destination, linear + source, bytes_per_block);
        }
    }
    return 1;
}
