export const PRODUCT_EDGES: Record<string, [string, string][]> = {
  'iPhone': [
    // Tier 2/3 to Tier 1
    ['TSMC_Hsinchu', 'Foxconn_Zhengzhou'],
    ['Samsung_Display_Seoul', 'Foxconn_Zhengzhou'],
    ['Sony_Kumamoto', 'Foxconn_Zhengzhou'],
    ['Corning_Kentucky', 'Foxconn_Zhengzhou'],
    ['SK_Hynix_Icheon', 'Foxconn_Zhengzhou'],
    ['Micron_Boise', 'Foxconn_Zhengzhou'],
    ['Cirrus_Logic_Austin', 'Foxconn_Zhengzhou'],
    ['NXP_Eindhoven', 'Foxconn_Zhengzhou'],
    ['STMicro_Geneva', 'Foxconn_Zhengzhou'],
    ['Broadcom_San_Jose', 'Foxconn_Zhengzhou'],
    ['Kioxia_Tokyo', 'Pegatron_Shanghai'],
    ['SK_Hynix_Icheon', 'Pegatron_Shanghai'],

    // Tier 1 to Distribution
    ['Foxconn_Zhengzhou', 'Port_of_Long_Beach'],
    ['Pegatron_Shanghai', 'Port_of_Long_Beach'],
  ],
  'AirPods': [
    // Components to Packaging / Assembly
    ['TSMC_Hsinchu', 'Amkor_Manila'],
    ['Amkor_Manila', 'Luxshare_Bac_Giang'],
    ['Murata_Kyoto', 'Luxshare_Bac_Giang'],
    ['GoerTek_Bac_Ninh', 'Luxshare_Bac_Giang'],
    ['Varta_Ellwangen', 'Luxshare_Bac_Giang'],
    ['TSMC_Hsinchu', 'Inventec_Taipei'],
  ],
  'Tesla Model Y': [
    // Raw Materials to Battery Cells
    ['Albemarle_Chile', 'CATL_Ningde'],
    ['Albemarle_Chile', 'LG_Energy_Nanjing'],
    ['Ganfeng_Lithium_Xinyu', 'CATL_Ningde'],
    ['Ganfeng_Lithium_Xinyu', 'LG_Energy_Nanjing'],

    // Battery Cells and Components to Assembly
    ['CATL_Ningde', 'Tesla_Berlin'],
    ['LG_Energy_Nanjing', 'Tesla_Berlin'],
    ['Panasonic_Nevada', 'Tesla_Berlin'],
    ['ZF_Friedrichshafen', 'Tesla_Berlin'],
    ['Bosch_Stuttgart', 'Tesla_Berlin'],
    ['Brembo_Bergamo', 'Tesla_Berlin'],
    ['Valeo_Paris', 'Tesla_Berlin'],
  ],
};
