#include "parser.h"

#include <string.h>

#include "crc.h"

static uint16_t parser_crc(const uint8_t *length_and_payload, size_t count)
{
    return crc16_ccitt(length_and_payload, count);
}

static parser_status_t parser_check_crc(const uint8_t *buf, size_t payload_len)
{
    uint16_t expected = parser_crc(&buf[1], 1u + payload_len);
    uint16_t received = (uint16_t)(((uint16_t)buf[2u + payload_len] << 8) |
                                   (uint16_t)buf[3u + payload_len]);

    return (expected == received) ? PARSER_OK : PARSER_ERR_BAD_CRC;
}

parser_status_t parser_parse(const uint8_t *buf, size_t len, parser_frame_t *frame)
{
    if (buf == NULL || frame == NULL) {
        return PARSER_ERR_NULL;
    }
    memset(frame, 0, sizeof(*frame));
    if (len < PARSER_OVERHEAD) {
        return PARSER_ERR_TRUNCATED;
    }
    if (buf[0] != PARSER_SOF) {
        return PARSER_ERR_BAD_SOF;
    }

    size_t payload_len = buf[1];
    if (payload_len > PARSER_MAX_PAYLOAD) {
        return PARSER_ERR_TOO_LONG;
    }
    if (len < PARSER_OVERHEAD + payload_len) {
        return PARSER_ERR_TRUNCATED;
    }

    frame->length = (uint8_t)payload_len;
    memcpy(frame->payload, &buf[2], payload_len);

    parser_status_t status = parser_check_crc(buf, payload_len);
    if (status != PARSER_OK) {
        memset(frame, 0, sizeof(*frame));
    }
    return status;
}

parser_status_t parser_encode(const uint8_t *payload, size_t payload_len,
                              uint8_t *out, size_t out_cap, size_t *out_len)
{
    if ((payload == NULL && payload_len > 0u) || out == NULL || out_len == NULL) {
        return PARSER_ERR_NULL;
    }
    if (payload_len > PARSER_MAX_PAYLOAD) {
        return PARSER_ERR_TOO_LONG;
    }
    if (out_cap < PARSER_OVERHEAD + payload_len) {
        return PARSER_ERR_TRUNCATED;
    }

    out[0] = PARSER_SOF;
    out[1] = (uint8_t)payload_len;
    if (payload_len > 0u) {
        memcpy(&out[2], payload, payload_len);
    }
    uint16_t crc = parser_crc(&out[1], 1u + payload_len);
    out[2u + payload_len] = (uint8_t)(crc >> 8);
    out[3u + payload_len] = (uint8_t)(crc & 0xFFu);
    *out_len = PARSER_OVERHEAD + payload_len;
    return PARSER_OK;
}
