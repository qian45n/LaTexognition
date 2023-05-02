import torch
import torch.nn as nn
from torch.nn.init import trunc_normal_
from x_transformers import Encoder
from einops import rearrange, repeat


class ViTransformerWrapper(nn.Module):
    def __init__(
        self,
        *,
        max_width,
        max_height,
        patch_size,
        attn_layers,
        channels=1,
        num_classes=None,
        dropout=0.,
        emb_dropout=0.
    ):
        super().__init__()
        assert isinstance(attn_layers, Encoder), 'attention layers must be an Encoder'
        assert max_width % patch_size == 0 and max_height % patch_size == 0, 'image dimensions must be divisible by the patch size'
        dim = attn_layers.dim
        num_patches = (max_width // patch_size)*(max_height // patch_size)
        patch_dim = channels * patch_size ** 2

        self.patch_size = patch_size
        self.max_width = max_width
        self.max_height = max_height

        self.pos_embedding = nn.Parameter(torch.randn(1, num_patches + 1, dim))
        self.patch_to_embedding = nn.Linear(patch_dim, dim)
        self.cls_token = nn.Parameter(torch.randn(1, 1, dim))
        self.dropout = nn.Dropout(emb_dropout)

        self.attn_layers = attn_layers
        self.norm = nn.LayerNorm(dim)
        #self.mlp_head = FeedForward(dim, dim_out = num_classes, dropout = dropout) if exists(num_classes) else None

    def forward(self, img, **kwargs):
        p = self.patch_size

        x = rearrange(img, 'b c (h p1) (w p2) -> b (h w) (p1 p2 c)', p1=p, p2=p)
        x = self.patch_to_embedding(x)
        b, n, _ = x.shape

        cls_tokens = repeat(self.cls_token, '() n d -> b n d', b=b)
        x = torch.cat((cls_tokens, x), dim=1)
        h, w = torch.tensor(img.shape[2:])//p
        pos_emb_ind = repeat(torch.arange(h)*(self.max_width//p-w), 'h -> (h w)', w=w)+torch.arange(h*w)
        pos_emb_ind = torch.cat((torch.zeros(1), pos_emb_ind+1), dim=0).long()
        x += self.pos_embedding[:, pos_emb_ind]
        x = self.dropout(x)

        x = self.attn_layers(x, **kwargs)
        x = self.norm(x)

        return x


class DeiTWrapper(nn.Module):
    def __init__(
        self,
        *,
        max_width,
        max_height,
        patch_size,
        attn_layers,
        channels=1,
        num_classes=None,
        emb_dropout=0.
    ):
        super().__init__()
        assert isinstance(attn_layers, nn.Module), 'attention layers must be an nn.Module'
        assert max_width % patch_size == 0 and max_height % patch_size == 0, 'image dimensions must be divisible by the patch size'
        dim = attn_layers.dim
        num_patches = (max_width // patch_size) * (max_height // patch_size)
        patch_dim = channels * patch_size ** 2

        self.patch_size = patch_size
        self.max_width = max_width
        self.max_height = max_height

        self.cls_token = nn.Parameter(torch.randn(1, 1, dim))
        self.dist_token = nn.Parameter(torch.randn(1, 1, dim))
        self.pos_embedding = nn.Parameter(torch.randn(1, num_patches + 1, dim))
        self.patch_to_embedding = nn.Linear(patch_dim, dim)
        self.dropout = nn.Dropout(emb_dropout)

        self.attn_layers = attn_layers
        self.norm = nn.LayerNorm(dim)
        
        self.head = nn.Linear(dim, num_classes) if num_classes is not None else nn.Identity()
        self.head_dist = nn.Linear(dim, num_classes) if num_classes is not None else nn.Identity()

        trunc_normal_(self.cls_token, std=.02)
        trunc_normal_(self.dist_token, std=.02)
        trunc_normal_(self.pos_embedding, std=.02)
        self.head.apply(self._init_weights)
        self.head_dist.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.zeros_(m.bias)

    def forward(self, img, **kwargs):
        p = self.patch_size

        x = rearrange(img, 'b c (h p1) (w p2) -> b (h w) (p1 p2 c)', p1=p, p2=p)
        x = self.patch_to_embedding(x)
        b, n, _ = x.shape

        cls_tokens = repeat(self.cls_token, '() n d -> b n d', b=b)
        dist_tokens = repeat(self.dist_token, '() n d -> b n d', b=b)
        x = torch.cat((cls_tokens, dist_tokens, x), dim=1)

        h, w = torch.tensor(img.shape[2:]) // p
        pos_emb_ind = repeat(torch.arange(h) * (self.max_width // p - w), 'h -> (h w)', w=w) + torch.arange(h * w)
        pos_emb_ind = torch.cat((torch.zeros(1), pos_emb_ind + 1), dim=0).long()
        x += self.pos_embedding[:, pos_emb_ind]
        x = self.dropout(x)

        x = self.attn_layers(x, **kwargs)
        x = self.norm(x)

        cls_output = self.head(x[:, 0])
        dist_output = self.head_dist(x[:, 1])

        if self.training:
            return cls_output, dist_output
        else:
            return (cls_output, dist_output)/2


def get_encoder(args):
    if args.encoder_type.lower() == 'vit':
        print('using ViT')
        return ViTransformerWrapper(
            max_width=args.max_width,
            max_height=args.max_height,
            channels=args.channels,
            patch_size=args.patch_size,
            emb_dropout=args.get('emb_dropout', 0),
            attn_layers=Encoder(
                dim=args.dim,
                depth=args.encoder_depth,
                heads=args.heads,
            )
        )
    elif args.encoder_type.lower()=='deit':
        print('using DeiT')
        return DeiTWrapper(
            max_width=args.max_width,
            max_height=args.max_height,
            channels=args.channels,
            patch_size=args.patch_size,
            emb_dropout=args.get('emb_dropout', 0),
            attn_layers=Encoder(
                dim=args.dim,
                depth=args.encoder_depth,
                heads=args.heads,
            )
        )
        '''
        Args:
            img_size (int, tuple): input image size
            patch_size (int, tuple): patch size
            in_chans (int): number of input channels
            num_classes (int): number of classes for classification head
            global_pool (str): type of global pooling for final sequence (default: 'token')
            embed_dim (int): embedding dimension
            depth (int): depth of transformer
            num_heads (int): number of attention heads
            mlp_ratio (int): ratio of mlp hidden dim to embedding dim
            qkv_bias (bool): enable bias for qkv if True
            init_values: (float): layer-scale init values
            class_token (bool): use class token
            fc_norm (Optional[bool]): pre-fc norm after pool, set if global_pool == 'avg' if None (default: None)
            drop_rate (float): dropout rate
            attn_drop_rate (float): attention dropout rate
            drop_path_rate (float): stochastic depth rate
            weight_init (str): weight init scheme
            embed_layer (nn.Module): patch embedding layer
            norm_layer: (nn.Module): normalization layer
            act_layer: (nn.Module): MLP activation layer
        """
        '''
