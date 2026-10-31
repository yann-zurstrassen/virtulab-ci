#ifndef PARSER_H
#define PARSER_H

#include <stddef.h>
#include <stdint.h>

/*
 * Wire format: [SOF][length][payload ... length bytes][CRC16 hi][CRC16 lo]
 * The CRC covers the length byte and the payload.
 */
#define PARSER_SOF 0xA5u
#define PARSER_MAX_PAYLOAD 32u
#define PARSER_OVERHEAD 4u
#define PARSER_MAX_FRAME (PARSER_MAX_PAYLOAD + PARSER_OVERHEAD)

typedef enum {
    PARSER_OK = 0,
    PARSER_ERR_NULL,
    PARSER_ERR_TRUNCATED,
    PARSER_ERR_BAD_SOF,
    PARSER_ERR_TOO_LONG,
    PARSER_ERR_BAD_CRC
} parser_status_t;

typedef struct {
    uint8_t length;
    uint8_t payload[PARSER_MAX_PAYLOAD];
} parser_frame_t;

/* On any error the frame is zeroed, so callers never see unauthenticated bytes. */
parser_status_t parser_parse(const uint8_t *buf, size_t len, parser_frame_t *frame);

parser_status_t parser_encode(const uint8_t *payload, size_t payload_len,
                              uint8_t *out, size_t out_cap, size_t *out_len);

#endif /* PARSER_H */
