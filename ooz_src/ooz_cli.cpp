#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstring>
#include <cstdlib>

// Inclui headers essenciais do ooz
#include "stdafx.h" // Importante para definições de tipos
#include "kraken.h"

// Fallback de compatibilidade se necessário
typedef unsigned char uint8;

// Função auxiliar para ler arquivo completo
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

// Função auxiliar para escrever arquivo
bool writeFile(const char* filename, const std::vector<uint8>& data) {
    std::ofstream file(filename, std::ios::binary);
    if (!file) return false;
    file.write((char*)data.data(), data.size());
    return true;
}

int main(int argc, char* argv[]) {
    // Uso: ./ooz_cli <mode> <input_file> <output_file> [size_if_decompress]
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

        // Tenta descomprimir usando a API padrão do Ooz
        // A função Kraken_Decompress deve estar disponível se o compilador tiver as flags AVX/SSE ativadas
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
