#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstring>
#include <cstdlib>

// Inclui headers essenciais do ooz
#include "stdafx.h"
#include "kraken.h"

// Fallback de compatibilidade
typedef unsigned char uint8;

// Declaração manual da função do ooz (Kraken) para garantir visibilidade
// A assinatura padrão do ooz para Kraken_Decompress
int Kraken_Decompress(const uint8 *src, size_t src_len, uint8 *dst, size_t dst_len);

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

        // Chama a função Kraken_Decompress diretamente
        int result = Kraken_Decompress(inputData.data(), inputData.size(), outputData.data(), decodedSize);
        
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
