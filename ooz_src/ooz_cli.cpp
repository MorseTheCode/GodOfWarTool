#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstring>
#include <cstdlib>

// Define types required by ooz headers if they are missing
typedef unsigned char uint8;
typedef unsigned char byte;

// Fix for __forceinline on Linux/GCC if stdafx.h doesn't handle it correctly
#ifndef __forceinline
#define __forceinline inline __attribute__((always_inline))
#endif

// Include headers
#include "stdafx.h"
#include "kraken.h"

// Explicit declaration of Kraken_Decompress to fix "not declared" error.
// The signature in ooz is usually:
// int Kraken_Decompress(const byte *src, size_t src_len, byte *dst, size_t dst_len);
// We use 'byte' which is typedef'd to unsigned char.
int Kraken_Decompress(const byte *src, size_t src_len, byte *dst, size_t dst_len);

std::vector<uint8> readFile(const char* filename) {
    std::ifstream file(filename, std::ios::binary);
    if (!file) return {};
    file.seekg(0, std::ios::end);
    size_t size = file.tellg();
    file.seekg(0, std::ios::beg);
    std::vector<uint8> buffer(size);
    file.read((char*)buffer.data(), size);
    return buffer;
}

bool writeFile(const char* filename, const std::vector<uint8>& data) {
    std::ofstream file(filename, std::ios::binary);
    if (!file) return false;
    file.write((char*)data.data(), data.size());
    return true;
}

int main(int argc, char* argv[]) {
    // Usage: ./ooz_cli <mode> <input_file> <output_file> [size_if_decompress]
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0] << " <mode> <input> <output> [size]" << std::endl;
        return 1;
    }

    std::string mode = argv[1];
    std::string inputFile = argv[2];
    std::string outputFile = argv[3];

    auto inputData = readFile(inputFile.c_str());
    if (inputData.empty()) {
        std::cerr << "Error: Could not read input file" << std::endl;
        return 1;
    }

    std::vector<uint8> outputData;

    if (mode == "d") { // Decompress
        if (argc < 5) {
            std::cerr << "Error: Decompression requires output size argument" << std::endl;
            return 1;
        }
        size_t decodedSize = std::stoull(argv[4]);
        outputData.resize(decodedSize);

        // Call Kraken_Decompress using the signature we declared above.
        // We cast pointers to (byte*) to match the declaration.
        int result = Kraken_Decompress((const byte*)inputData.data(), inputData.size(), (byte*)outputData.data(), decodedSize);
        
        if (result <= 0) {
            std::cerr << "Error: Decompression failed with code " << result << std::endl;
            return 2;
        }
    } 
    else {
        std::cerr << "Error: Unknown mode " << mode << std::endl;
        return 1;
    }

    if (!writeFile(outputFile.c_str(), outputData)) {
        std::cerr << "Error: Could not write output file" << std::endl;
        return 1;
    }

    return 0;
}
