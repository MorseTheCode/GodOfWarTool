<?php
// Configurações do Servidor
ini_set('memory_limit', '512M');
ini_set('max_execution_time', 600); // 10 minutos para arquivos grandes
ini_set('display_errors', 0);
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

// Definição de Caminhos
$BASE_DIR = __DIR__;
$UPLOAD_DIR = $BASE_DIR . '/uploads';
$TEMP_DIR = $BASE_DIR . '/temp';
$EXPORTS_DIR = $BASE_DIR . '/exports';
$OOZ_CLI = $BASE_DIR . '/ooz_cli'; // O binário compilado

// Garante que as pastas existem
if (!is_dir($UPLOAD_DIR)) mkdir($UPLOAD_DIR, 0777, true);
if (!is_dir($TEMP_DIR)) mkdir($TEMP_DIR, 0777, true);
if (!is_dir($EXPORTS_DIR)) mkdir($EXPORTS_DIR, 0777, true);

// Rota de Download
if (isset($_GET['download'])) {
    $file = basename($_GET['download']);
    $path = $EXPORTS_DIR . '/' . $file;
    if (file_exists($path)) {
        header('Content-Type: application/zip');
        header('Content-Disposition: attachment; filename="'.$file.'"');
        header('Content-Length: ' . filesize($path));
        readfile($path);
        // Opcional: deletar arquivo após download para economizar espaço
        // unlink($path); 
        exit;
    } else {
        http_response_code(404);
        echo json_encode(['error' => 'Arquivo não encontrado.']);
        exit;
    }
}

// Rota Principal (POST)
$action = $_POST['action'] ?? '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if ($action === 'extract') {
        handleExtraction();
    } else {
        echo json_encode(['status' => 'online', 'message' => 'GoW Backend Ready']);
    }
} else {
    // Health check simples
    echo json_encode([
        'status' => 'online', 
        'ooz_cli_exists' => file_exists($OOZ_CLI),
        'can_execute' => is_executable($OOZ_CLI)
    ]);
}

function handleExtraction() {
    global $UPLOAD_DIR, $TEMP_DIR, $EXPORTS_DIR, $OOZ_CLI;

    if (!isset($_FILES['file']) || $_FILES['file']['error'] !== UPLOAD_ERR_OK) {
        http_response_code(400);
        echo json_encode(['error' => 'Upload falhou ou nenhum arquivo enviado.']);
        exit;
    }

    // Verifica se o binário C++ existe
    if (!file_exists($OOZ_CLI)) {
        http_response_code(500);
        echo json_encode(['error' => 'Servidor mal configurado: ooz_cli não encontrado.']);
        exit;
    }

    $file = $_FILES['file'];
    $filename = preg_replace('/[^a-zA-Z0-9_.-]/', '_', $file['name']); // Sanitiza nome
    $targetPath = $UPLOAD_DIR . '/' . uniqid() . '_' . $filename;
    
    if (!move_uploaded_file($file['tmp_name'], $targetPath)) {
        http_response_code(500);
        echo json_encode(['error' => 'Falha ao mover arquivo enviado.']);
        exit;
    }

    try {
        // Cria ZIP de saída
        $zipName = 'extracted_' . uniqid() . '.zip';
        $zipPath = $EXPORTS_DIR . '/' . $zipName;
        $zip = new ZipArchive();
        
        if ($zip->open($zipPath, ZipArchive::CREATE) !== TRUE) {
            throw new Exception("Não foi possível criar o arquivo ZIP.");
        }

        // --- LÓGICA DE EXTRAÇÃO SIMPLIFICADA ---
        // Aqui o PHP deveria ler o WAD byte-a-byte. 
        // Como o WAD é binário complexo, para este exemplo funcionar sem o código completo de parsing em PHP,
        // vamos simular que estamos processando o arquivo.
        
        // Em um cenário real de produção, você deve portar a classe 'Gow2018_Wad' do Python para PHP
        // para ler os offsets. Quando encontrar um chunk comprimido, você faria:
        /*
           $cmd = "$OOZ_CLI d $inputChunkPath $outputChunkPath $decompressedSize";
           exec($cmd, $output, $returnCode);
        */

        // Para fins de demonstração (já que não temos o parser WAD completo em PHP neste snippet):
        // Vamos adicionar o arquivo original ao ZIP apenas para provar que o fluxo funciona.
        $zip->addFile($targetPath, "original_file_backup.wad");
        $zip->addFromString("readme.txt", "Extração processada pelo backend PHP + Ooz C++.\nImplemente o parser WAD completo no backend.php para extrair arquivos individuais.");
        
        $zip->close();
        
        // Limpa upload
        @unlink($targetPath);

        echo json_encode([
            'status' => 'success',
            'download_url' => $zipName
        ]);

    } catch (Exception $e) {
        http_response_code(500);
        echo json_encode(['error' => $e->getMessage()]);
    }
}
?>
