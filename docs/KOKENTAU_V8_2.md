# Kokentau V8.2

O pacote da aplicação contém a referência Python. A inferência cromática usa dois checkpoints do pacote V7. Grade, época 75, aprende uma transformação RGB afim local em grade bilateral. AdaptiveV7, época 42, combina quatro especialistas com um resíduo convolucional. O manifesto e o checkpoint adaptativo vinculam os dois pesos e identificam o núcleo de referência.

O pacote V8 fornecido contém ROI e manifestos, com uma lista vazia de cabeças de segmentação. O núcleo aceita RGB de 8 bits com orientação EXIF aplicada. A região é recortada e, onde necessário, pixels externos do recorte são temporariamente preenchidos pelo pixel interno mais próximo. O operador mascarado e o V7 são combinados em proporção 40/60. A intensidade padrão é 0,85. O componente estrutural gera mapas independentes e contribui para o resultado combinado. Fora da ROI, o resultado cromático e combinado preserva os pixels de entrada.

O editor usa ROI retangular manual ou fotografia inteira mediante confirmação. O pacote de metadados é validado, mas o editor ainda não resolve ROIs históricas por identificadores de lote. Segmentação, SAM2, restauração opcional e ingestão de lotes da referência permanecem pendentes.

## Comparação local

A referência original e o adaptador foram executados em CPU, com o mesmo par de pesos, imagem sintética RGB de 176 × 140 pixels gerada com NumPy seed 42, retângulo X 11–155 e Y 10–120, intensidade 0,85 e bloco de 64. As 11 saídas foram comparadas com igualdade exata de pixels. O original fora da ROI permaneceu idêntico. A referência levou cerca de 0,26 segundo nessa execução, sem incluir inicialização ou carga de pesos. A medição descreve somente essa amostra.

A comparação estabelece paridade numérica nessa amostra e não constitui validação arqueológica. Fotografias, pesos e arquivos intermediários permanecem locais. CUDA, desempenho em fotografias grandes e equivalência em imagens reais ainda exigem validação.
