#ifndef INC_UNI_NLU_CONTENT_H_
#define INC_UNI_NLU_CONTENT_H_

typedef struct {
  uni_u32 key_word_hash_code; /* 存放识别词汇对应的hashcode */
  uni_u8  nlu_content_str_index; /* 存放nlu映射表中的索引，实现多个识别词汇可对应同一个nlu，暂支持256条，如果不够换u16 */
  char    *hash_collision_orginal_str /* 类似Java String equal，当hash发生碰撞时，赋值为识别词汇，否则设置为NULL */;
} uni_nlu_content_mapping_t;

enum {
  eCMD_wakeup_uni,
  eCMD_exitUni,
  eCMD_Style0,
  eCMD_Style1,
  eCMD_Style2,
  eCMD_ViewNext,
};

const char* const g_nlu_content_str[] = {
[eCMD_wakeup_uni] = "{\"asr\":\"小安小安\",\"cmd\":\"wakeup_uni\",\"pcm\":\"[103, 104, 105]\"}",
[eCMD_exitUni] = "{\"asr\":\"退出\",\"cmd\":\"exitUni\",\"pcm\":\"[106]\"}",
[eCMD_Style0] = "{\"asr\":\"切换梵高\",\"cmd\":\"Style0\",\"pcm\":\"[107]\"}",
[eCMD_Style1] = "{\"asr\":\"切换浮世绘\",\"cmd\":\"Style1\",\"pcm\":\"[108]\"}",
[eCMD_Style2] = "{\"asr\":\"切换水墨\",\"cmd\":\"Style2\",\"pcm\":\"[109]\"}",
[eCMD_ViewNext] = "{\"asr\":\"切换画面\",\"cmd\":\"ViewNext\",\"pcm\":\"[110]\"}",
};

/*TODO perf sort by hashcode O(logN), now version O(N)*/
const uni_nlu_content_mapping_t g_nlu_content_mapping[] = {
  {3495814520U/*小安小安*/, eCMD_wakeup_uni, NULL},
  {2497873263U/*退出*/, eCMD_exitUni, NULL},
  {1175503444U/*切换梵高*/, eCMD_Style0, NULL},
  {3554831114U/*切换浮世绘*/, eCMD_Style1, NULL},
  {1188398840U/*切换水墨*/, eCMD_Style2, NULL},
  {1191381623U/*切换画面*/, eCMD_ViewNext, NULL},
};

#endif
