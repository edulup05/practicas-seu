#include <edu_lupion-project-1_inferencing.h>

#include "esp_camera.h"
#include "img_converters.h"
#include <WiFi.h>
#include "board_config.h"

#include "edge-impulse-sdk/dsp/image/image.hpp"

// ── Credenciales WiFi ─────────────────────────────────────────────────────────

const char *WIFI_SSID = "Kris";
const char *WIFI_PWD  = "1234567890";

// ── Declaraciones externas ────────────────────────────────────────────────────

void startCameraServer();
void setupLedFlash();
extern "C" void ei_push_result(const char *json);   // definida en app_httpd.cpp

// ── Buffer de entrada para Edge Impulse ──────────────────────────────────────
//
// crop_and_interpolate_rgb888 opera in-place sobre este buffer.
// El crop intermedio puede ser considerablemente mayor que 96×96:
// para QVGA (320×240) el cuadrado central es 240×240 = 172 800 B.
// Se reserva el peor caso posible para QVGA: 320×240×3 = 230 400 B.

static const size_t   EI_BUF_SIZE         = 320 * 240 * 3;
static uint8_t       *ei_frame_buf        = nullptr;
static const uint32_t INFERENCE_PERIOD_MS = 500;

// ── Inicialización ────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println();
    Serial.println("===== BOOT =====");

    // Configuración del sensor de cámara
    camera_config_t camCfg;
    camCfg.ledc_channel  = LEDC_CHANNEL_0;
    camCfg.ledc_timer    = LEDC_TIMER_0;
    camCfg.pin_d0        = Y2_GPIO_NUM;
    camCfg.pin_d1        = Y3_GPIO_NUM;
    camCfg.pin_d2        = Y4_GPIO_NUM;
    camCfg.pin_d3        = Y5_GPIO_NUM;
    camCfg.pin_d4        = Y6_GPIO_NUM;
    camCfg.pin_d5        = Y7_GPIO_NUM;
    camCfg.pin_d6        = Y8_GPIO_NUM;
    camCfg.pin_d7        = Y9_GPIO_NUM;
    camCfg.pin_xclk      = XCLK_GPIO_NUM;
    camCfg.pin_pclk      = PCLK_GPIO_NUM;
    camCfg.pin_vsync     = VSYNC_GPIO_NUM;
    camCfg.pin_href      = HREF_GPIO_NUM;
    camCfg.pin_sccb_sda  = SIOD_GPIO_NUM;
    camCfg.pin_sccb_scl  = SIOC_GPIO_NUM;
    camCfg.pin_pwdn      = PWDN_GPIO_NUM;
    camCfg.pin_reset     = RESET_GPIO_NUM;
    camCfg.xclk_freq_hz  = 20000000;
    camCfg.frame_size    = FRAMESIZE_QVGA;
    camCfg.pixel_format  = PIXFORMAT_JPEG;
    camCfg.grab_mode     = CAMERA_GRAB_LATEST;
    camCfg.fb_location   = CAMERA_FB_IN_PSRAM;
    camCfg.jpeg_quality  = 12;
    camCfg.fb_count      = 2;

    // Sin PSRAM: reducir resolución y usar DRAM
    if (!psramFound()) {
        camCfg.frame_size  = FRAMESIZE_QQVGA;
        camCfg.fb_location = CAMERA_FB_IN_DRAM;
        camCfg.fb_count    = 1;
    }

    esp_err_t camErr = esp_camera_init(&camCfg);
    if (camErr != ESP_OK) {
        Serial.printf("Error al iniciar cámara: 0x%x\n", camErr);
        return;
    }

    // Ajustes específicos para el sensor OV3660
    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor->id.PID == OV3660_PID) {
        sensor->set_vflip(sensor, 1);
        sensor->set_brightness(sensor, 1);
        sensor->set_saturation(sensor, -2);
    }
    sensor->set_framesize(sensor, FRAMESIZE_QVGA);

    // Reserva el buffer de entrada para el clasificador en PSRAM
    ei_frame_buf = (uint8_t *)ps_malloc(EI_BUF_SIZE);
    if (!ei_frame_buf) {
        Serial.println("[EI] Fallo al reservar buffer en PSRAM");
        while (true) { delay(1000); }
    }

#if defined(LED_GPIO_NUM)
    setupLedFlash();
#endif

    // Conexión WiFi con timeout de 15 s
    WiFi.begin(WIFI_SSID, WIFI_PWD);
    WiFi.setSleep(false);
    Serial.print("Conectando WiFi");
    uint32_t wifiStart = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WiFi conectado");
        startCameraServer();
        Serial.print("Cámara lista en http://");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("Timeout WiFi — modo inferencia solo por Serial");
    }
}

// ── Callback de datos para Edge Impulse ──────────────────────────────────────
//
// Convierte el buffer RGB888 (orden B-G-R en memoria) al entero empaquetado
// que espera el SDK: 0x00RRGGBB.

static int ei_get_pixel_data(size_t offset, size_t length, float *out_ptr) {
    size_t px  = offset * 3;
    size_t idx = 0;
    while (length-- != 0) {
        out_ptr[idx++] = (ei_frame_buf[px + 2] << 16)
                       + (ei_frame_buf[px + 1] <<  8)
                       +  ei_frame_buf[px];
        px += 3;
    }
    return 0;
}

// ── Ciclo de inferencia ───────────────────────────────────────────────────────

static void run_inference() {
    // Captura un frame de la cámara
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { Serial.println("[CAM] fb_get devolvió NULL"); return; }

    uint16_t srcW = fb->width;
    uint16_t srcH = fb->height;

    // Convierte JPEG → RGB888 en un buffer temporal en PSRAM
    uint8_t *rgbBuf = (uint8_t *)ps_malloc(srcW * srcH * 3);
    if (!rgbBuf) { esp_camera_fb_return(fb); return; }

    bool converted = fmt2rgb888(fb->buf, fb->len, fb->format, rgbBuf);
    esp_camera_fb_return(fb);
    if (!converted) { free(rgbBuf); return; }

    // Recorta y redimensiona al tamaño de entrada del modelo (96×96)
    ei::image::processing::crop_and_interpolate_rgb888(
        rgbBuf, srcW, srcH,
        ei_frame_buf,
        EI_CLASSIFIER_INPUT_WIDTH,
        EI_CLASSIFIER_INPUT_HEIGHT);
    free(rgbBuf);

    // Prepara la señal de entrada para el clasificador
    signal_t signal;
    signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
    signal.get_data     = &ei_get_pixel_data;

    // Ejecuta el clasificador
    ei_impulse_result_t result = { 0 };
    EI_IMPULSE_ERROR classErr = run_classifier(&signal, &result, false);
    if (classErr != EI_IMPULSE_OK) {
        Serial.printf("[EI] Error en run_classifier: %d\n", classErr);
        return;
    }

    Serial.printf("[EI] DSP %d ms | Clasificación %d ms\n",
                  result.timing.dsp, result.timing.classification);

    // Serializa las detecciones en JSON y las publica en el endpoint /results.
    // Las coordenadas se expresan en el espacio 96×96 del modelo; el cliente
    // las escala al tamaño del stream usando EI_CLASSIFIER_INPUT_WIDTH/HEIGHT.
    char jsonOut[1024];
    int  written = snprintf(jsonOut, sizeof(jsonOut),
                            "{\"timing\":{\"dsp\":%d,\"nn\":%d},"
                            "\"model_w\":%d,\"model_h\":%d,\"detections\":[",
                            result.timing.dsp, result.timing.classification,
                            EI_CLASSIFIER_INPUT_WIDTH, EI_CLASSIFIER_INPUT_HEIGHT);

    bool firstBox = true;
    for (uint32_t i = 0;
         i < result.bounding_boxes_count && written < (int)sizeof(jsonOut) - 2;
         i++) {
        auto &bb = result.bounding_boxes[i];
        if (bb.value < EI_CLASSIFIER_OBJECT_DETECTION_THRESHOLD) continue;

        written += snprintf(jsonOut + written, sizeof(jsonOut) - written,
                            "%s{\"label\":\"%s\",\"conf\":%.2f,"
                            "\"x\":%u,\"y\":%u,\"w\":%u,\"h\":%u}",
                            firstBox ? "" : ",",
                            bb.label, bb.value,
                            bb.x, bb.y, bb.width, bb.height);
        firstBox = false;

        Serial.printf("  [BB] %s (%.2f) x=%u y=%u w=%u h=%u\n",
                      bb.label, bb.value, bb.x, bb.y, bb.width, bb.height);
    }
    snprintf(jsonOut + written, sizeof(jsonOut) - written, "]}");

    ei_push_result(jsonOut);
    if (firstBox) Serial.println("  [BB] Sin detecciones");
}

// ── Bucle principal ───────────────────────────────────────────────────────────

void loop() {
    static uint32_t lastRun = 0;
    if (millis() - lastRun >= INFERENCE_PERIOD_MS) {
        lastRun = millis();
        run_inference();
    }
    delay(10);
}