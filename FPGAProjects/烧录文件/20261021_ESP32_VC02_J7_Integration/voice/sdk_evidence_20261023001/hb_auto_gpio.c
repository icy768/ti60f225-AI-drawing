#include "user_config.h"
#include "user_event.h"
#include "user_gpio.h"
#include "user_player.h"
#include "user_pwm.h"
#include "user_timer.h"
#include "user_uart.h"

#define TAG "auto_gpio"

#define UART_SEND_MAX      16

typedef struct {
  char  data[UART_SEND_MAX];
  int   len;
}uart_data_t;

const uart_data_t g_uart_buf[] = {
  {{0xA1, 0x00, 0x01, 0x01, 0xFF}, 5}, //Style0
  {{0xA1, 0x00, 0x02, 0x01, 0xFF}, 5}, //Style1
  {{0xA1, 0x00, 0x03, 0x01, 0xFF}, 5}, //Style2
  {{0xA1, 0x00, 0x04, 0x01, 0xFF}, 5}, //ViewNext
};

static void _custom_setting_cb(USER_EVENT_TYPE event,
                               user_event_context_t *context) {
  event_custom_setting_t *setting = NULL;
  if (context) {
    setting = &context->custom_setting;
    LOGT(TAG, "user command: %s", setting->cmd);
    if (0 == uni_strcmp(setting->cmd, "Style0")) {
      user_uart_send(g_uart_buf[0].data, g_uart_buf[0].len);
    } else if (0 == uni_strcmp(setting->cmd, "Style1")) {
      user_uart_send(g_uart_buf[1].data, g_uart_buf[1].len);
    } else if (0 == uni_strcmp(setting->cmd, "Style2")) {
      user_uart_send(g_uart_buf[2].data, g_uart_buf[2].len);
    } else if (0 == uni_strcmp(setting->cmd, "ViewNext")) {
      user_uart_send(g_uart_buf[3].data, g_uart_buf[3].len);
    } else {
      LOGT(TAG, "Unconcerned command: %s", setting->cmd);
    }
    user_player_reply_list_random(setting->reply_files);
  }
}

static void _register_event_callback(void) {
  user_event_subscribe_event(USER_CUSTOM_SETTING, _custom_setting_cb);
}

int hb_auto_gpio(void) {
  user_gpio_init();
  user_gpio_set_mode(GPIO_NUM_A25, GPIO_MODE_OUT);
  user_gpio_set_value(GPIO_NUM_A25, 0);
  user_gpio_set_mode(GPIO_NUM_A26, GPIO_MODE_OUT);
  user_gpio_set_value(GPIO_NUM_A26, 0);
  user_gpio_set_mode(GPIO_NUM_A27, GPIO_MODE_OUT);
  user_gpio_set_value(GPIO_NUM_A27, 0);
  user_gpio_set_mode(GPIO_NUM_A28, GPIO_MODE_OUT);
  user_gpio_set_value(GPIO_NUM_A28, 0);
  user_gpio_set_mode(GPIO_NUM_B2, GPIO_MODE_OUT);
  user_gpio_set_value(GPIO_NUM_B2, 0);
  user_gpio_set_mode(GPIO_NUM_B3, GPIO_MODE_OUT);
  user_gpio_set_value(GPIO_NUM_B3, 0);
  user_uart_init(NULL);
  _register_event_callback();
  return 0;
}

